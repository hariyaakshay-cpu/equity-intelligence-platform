"""
Instrument Synchronization Service for the Equity Intelligence Platform.

This service synchronizes the master instrument list from Upstox with the local
database, upserting NSE equity instruments into the Company model while avoiding
duplicates. It tracks all synchronization metrics and handles partial failures
gracefully within a transaction.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.providers import UpstoxProvider
from core.models.company import Company
from core.database import get_db_session

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """
    Data transfer object containing synchronization metrics.

    Attributes:
        total_received: Total instruments received from Upstox
        inserted: Number of new company records inserted
        updated: Number of existing company records updated
        skipped: Number of instruments skipped (non-NSE, non-equity, etc.)
        failed: Number of instruments that failed to process
        duration: Total time taken for synchronization in seconds
        timestamp: UTC timestamp when synchronization completed
    """
    total_received: int
    inserted: int
    updated: int
    skipped: int
    failed: int
    duration: float
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert the sync result to a dictionary for logging/serialization."""
        return {
            "total_received": self.total_received,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "duration_seconds": round(self.duration, 2),
            "timestamp": self.timestamp.isoformat()
        }


class InstrumentSyncService:
    """
    Service to synchronize instrument master data from Upstox into the local database.

    This service handles downloading, filtering, normalizing, and upserting NSE equity
    instruments into the Company model. It runs in a single transaction to ensure
    data consistency and provides detailed metrics about the synchronization process.
    """

    # Filter only NSE equity instruments (Equity, preference shares, debentures - not derivatives)
    SUPPORTED_INSTRUMENT_TYPES = {"EQ", "Preference", "Debenture"}
    TARGET_EXCHANGE = "NSE"

    def __init__(self, upstox_provider: UpstoxProvider):
        """
        Initialize the synchronization service with its dependencies.

        Args:
            upstox_provider: Initialized UpstoxProvider instance to fetch instrument data.
        """
        self.upstox_provider = upstox_provider

    def _normalize_instrument(self, instrument: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize raw Upstox instrument data to match the Company model schema.

        Args:
            instrument: Raw Instrument object from UpstoxProvider.

        Returns:
            Dictionary of normalized fields ready for database insertion/update,
            or None if the instrument should be skipped.
        """
        # Skip if not our target exchange or instrument type
        if instrument.exchange != self.TARGET_EXCHANGE:
            return None
        
        if instrument.instrument_type not in self.SUPPORTED_INSTRUMENT_TYPES:
            return None

        # Extract clean symbol without exchange prefix
        symbol = instrument.symbol.split(":")[1] if ":" in instrument.symbol else instrument.symbol

        return {
            "symbol": symbol,
            "company_name": instrument.name.strip() if instrument.name else "",
            "exchange": instrument.exchange,
            "sector": None,  # Sector data not available in master instrument list - can be enriched later
            "industry": None,  # Industry data not available in master instrument list - can be enriched later
            "market_cap": None,  # Market cap not available in master list - can be updated via fundamentals
            "isin": instrument.isin,
            "is_active": True,  # All instruments from master list are active by default
        }

    def sync(self) -> SyncResult:
        """
        Execute the full instrument synchronization process.

        This method:
        1. Downloads all instruments from Upstox
        2. Filters and normalizes NSE equity instruments
        3. Upserts valid instruments into the database within a transaction
        4. Tracks and logs all metrics
        5. Handles partial failures gracefully

        Returns:
            SyncResult object with complete synchronization metrics.

        Raises:
            RuntimeError: If a critical failure occurs that aborts the entire sync.
        """
        start_time = time.time()
        logger.info("Starting instrument synchronization process")

        # Initialize counters (use dict for mutable state in nested function)
        counters = {
            "total_received": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0
        }

        try:
            # Step 1: Download all instruments from Upstox
            logger.debug("Downloading instrument master from Upstox")
            raw_instruments = self.upstox_provider.get_instruments()
            counters["total_received"] = len(raw_instruments)
            logger.info(f"Received {counters['total_received']} total instruments from Upstox")

            # Step 2: Filter and normalize all valid instruments
            normalized_instruments: List[Dict[str, Any]] = []
            for raw_inst in raw_instruments:
                normalized = self._normalize_instrument(raw_inst)
                if normalized:
                    normalized_instruments.append(normalized)
                else:
                    counters["skipped"] += 1

            logger.info(f"Normalized {len(normalized_instruments)} valid NSE equity instruments, skipped {counters['skipped']}")

            # Step 3: Process all normalized instruments within a single transaction
            with get_db_session() as session:
                for norm_inst in normalized_instruments:
                    try:
                        new_inserts, new_updates = self._process_single_instrument(session, norm_inst)
                        counters["inserted"] += new_inserts
                        counters["updated"] += new_updates
                    except Exception as e:
                        counters["failed"] += 1
                        logger.error(f"Failed to process instrument {norm_inst['symbol']}: {str(e)}", exc_info=True)
                        continue

            # Calculate final duration
            duration = time.time() - start_time
            sync_result = SyncResult(
                total_received=counters["total_received"],
                inserted=counters["inserted"],
                updated=counters["updated"],
                skipped=counters["skipped"],
                failed=counters["failed"],
                duration=duration,
                timestamp=datetime.now(UTC)
            )

            # Log the final result
            logger.info(f"Instrument synchronization completed successfully. Metrics: {sync_result.to_dict()}")
            return sync_result

        except Exception as e:
            duration = time.time() - start_time
            logger.critical(f"Critical failure during instrument synchronization: {str(e)}. Duration: {round(duration, 2)}s", exc_info=True)
            raise RuntimeError(f"Instrument sync failed critically: {str(e)}") from e

    def _process_single_instrument(
        self,
        session: Session,
        normalized_inst: Dict[str, Any],
    ) -> tuple[int, int]:
        """
        Process a single normalized instrument - check if it exists, update or insert.

        Args:
            session: Active SQLAlchemy database session.
            normalized_inst: Normalized instrument data dictionary.

        Returns:
            Tuple containing (new_inserted, new_updated) - 0 or 1 for each counter.

        Raises:
            SQLAlchemyError: If a database error occurs while processing.
        """
        new_inserted = 0
        new_updated = 0
        symbol = normalized_inst["symbol"]
        
        # Check if company already exists
        existing = session.execute(
            select(Company).where(Company.symbol == symbol)
        ).scalar_one_or_none()

        if existing:
            # Update existing record
            update_count = 0
            # Only update fields that are safe to update
            if existing.company_name != normalized_inst["company_name"]:
                existing.company_name = normalized_inst["company_name"]
                update_count += 1
            if existing.isin != normalized_inst["isin"]:
                existing.isin = normalized_inst["isin"]
                update_count += 1
            if not existing.is_active:
                existing.is_active = True
                update_count += 1

            if update_count > 0:
                new_updated = 1
                logger.debug(f"Updated existing company: {symbol} ({update_count} fields changed)")
            else:
                logger.debug(f"No changes needed for existing company: {symbol}")
        else:
            # Insert new record
            new_company = Company(**normalized_inst)
            session.add(new_company)
            new_inserted = 1
            logger.debug(f"Inserted new company: {symbol}")

        return (new_inserted, new_updated)
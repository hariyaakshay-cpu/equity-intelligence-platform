"""
Daily Upstox sync job.

Usage:
    python -m jobs.daily_sync                         # all NSE equities, incremental
    python -m jobs.daily_sync --symbols RELIANCE,TCS  # selected symbols
    python -m jobs.daily_sync --schedule 18:30        # run daily at 18:30 IST

Each run loads the instrument master, then fetches prices from the day after
each company's latest stored price (or --days back for new companies).
Exits non-zero if any company failed, so cron/monitoring can alert.
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import Settings
from config.logging_config import setup_logging
from core.database import get_db_session, initialize_database
from core.models import Company, PriceHistory
from services.ingestion import sync_companies, sync_prices
from services.upstox import UpstoxClient, auth

logger = logging.getLogger(__name__)

IST_TZ = "Asia/Kolkata"


@dataclass
class SyncSummary:
    """Outcome of one sync run."""

    companies: int = 0
    price_rows: int = 0
    failed: dict[str, str] = field(default_factory=dict)


def run_sync(
    session: Session,
    client: UpstoxClient,
    *,
    exchange: str = "NSE",
    symbols: Optional[list[str]] = None,
    days: int = 365,
    skip_companies: bool = False,
    today: Optional[date] = None,
    delay: float = 0.0,
) -> SyncSummary:
    """
    Sync companies and incremental daily prices.

    Args:
        session: Database session; committed per company so one failure
            does not lose other companies' data.
        client: Upstox client.
        exchange: Exchange to load.
        symbols: Optional allow-list of symbols.
        days: Lookback for companies with no stored prices.
        skip_companies: Skip the instrument master refresh.
        today: Override for the current date (testing).
        delay: Seconds to sleep between companies (rate limiting).
    """
    today = today or date.today()
    summary = SyncSummary()

    if not skip_companies:
        sync_companies(session, client, exchange, symbols)
        session.commit()

    query = select(Company).where(Company.is_active, Company.isin.is_not(None))
    if symbols:
        query = query.where(Company.symbol.in_([s.upper() for s in symbols]))
    companies = session.scalars(query.order_by(Company.symbol)).all()
    summary.companies = len(companies)

    for company in companies:
        last = session.scalar(
            select(func.max(PriceHistory.trade_date)).where(PriceHistory.company_id == company.id)
        )
        start = last + timedelta(days=1) if last else today - timedelta(days=days)
        if start > today:
            continue
        try:
            summary.price_rows += sync_prices(session, client, company, start, today)
            session.commit()
        except Exception as e:  # keep going; report at the end
            session.rollback()
            summary.failed[company.symbol] = str(e)
            logger.error("Price sync failed for %s: %s", company.symbol, e)
        if delay:
            time.sleep(delay)
    return summary


def _resolve_token(settings: Settings) -> str:
    """Prefer a valid cached token from `jobs.upstox_auth`, else UPSTOX_ACCESS_TOKEN."""
    return auth.load_token() or settings.UPSTOX_ACCESS_TOKEN


def _run_once(args: argparse.Namespace, settings: Settings) -> int:
    client = UpstoxClient(_resolve_token(settings), settings.UPSTOX_BASE_URL)
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    with get_db_session() as session:
        summary = run_sync(
            session, client, exchange=args.exchange, symbols=symbols,
            days=args.days, skip_companies=args.skip_companies, delay=args.delay,
        )
    logger.info(
        "Sync done: %d companies, %d price rows, %d failed",
        summary.companies, summary.price_rows, len(summary.failed),
    )
    return 1 if summary.failed else 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(description="Daily Upstox price sync")
    p.add_argument("--exchange", default="NSE")
    p.add_argument("--symbols", help="Comma-separated symbols (default: all)")
    p.add_argument("--days", type=int, default=365, help="Lookback for new companies")
    p.add_argument("--skip-companies", action="store_true", help="Skip instrument refresh")
    p.add_argument("--delay", type=float, default=0.2, help="Seconds between companies")
    p.add_argument("--schedule", metavar="HH:MM", help="Run daily at this IST time (blocks)")
    args = p.parse_args(argv)

    settings = Settings()
    setup_logging(settings)
    initialize_database(settings)

    if not _resolve_token(settings):
        logger.error("No valid Upstox token; run `python -m jobs.upstox_auth`")
        return 2

    if not args.schedule:
        return _run_once(args, settings)

    from apscheduler.schedulers.blocking import BlockingScheduler

    hour, minute = (int(x) for x in args.schedule.split(":"))
    scheduler = BlockingScheduler(timezone=IST_TZ)
    scheduler.add_job(_run_once, "cron", args=[args, settings], hour=hour, minute=minute)
    logger.info("Scheduled daily sync at %02d:%02d IST", hour, minute)
    scheduler.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

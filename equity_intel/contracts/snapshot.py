"""PriceFetchSnapshot contract -- one immutable, append-only fetched candle.

Never updated or deleted once written -- see
docs/architecture/equity_intel_scanner_v1_spec.md, Section 8. This module
defines shape only; the canonical content_hash algorithm (SHA-256 of
"YYYY-MM-DD|open|high|low|close|volume", Decimal prices quantized to 2dp
with ROUND_HALF_UP, integer volume, empty string for null) is computed by
the acquisition/snapshot-writing code, not here.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional, Tuple


class CandleValidationStatus(str, enum.Enum):
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(frozen=True)
class PriceFetchSnapshot:
    scan_run_id: str
    symbol: str
    trading_date: str
    source: str
    fetched_at_ist: str
    open: Optional[Decimal]
    high: Optional[Decimal]
    low: Optional[Decimal]
    close: Optional[Decimal]
    volume: Optional[int]
    content_hash: str
    candle_validation_status: CandleValidationStatus
    validation_errors: Tuple[str, ...] = field(default_factory=tuple)
    source_metadata: Dict[str, str] = field(default_factory=dict)

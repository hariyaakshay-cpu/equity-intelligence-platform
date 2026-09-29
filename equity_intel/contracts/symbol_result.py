"""SymbolScanResult contract -- per-symbol classification outcome for one
ScanRun.

symbol_data_status reuses the existing DataStatus vocabulary
(VALID/INSUFFICIENT_HISTORY/STALE/FAILED) from equity_intel.contracts.quality
-- those four values, checked in that priority order, are exactly what
docs/architecture/equity_intel_scanner_v1_spec.md, Section 6, fixes for
symbol classification.

The four flag fields are independent booleans, per spec Section 6: a symbol
can carry any combination of them regardless of its symbol_data_status (a
VALID symbol may still carry HISTORY_GAPS, and independently
CORPORATE_ACTION_REVIEW and/or PRICE_BREAK_DETECTED and/or NON_EQ_SERIES).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from equity_intel.contracts.quality import DataStatus


@dataclass(frozen=True)
class SymbolScanResult:
    scan_run_id: str
    symbol: str
    symbol_data_status: DataStatus
    instrument_key: Optional[str] = None
    isin: Optional[str] = None
    series: Optional[str] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    status_reason: Optional[str] = None
    available_session_count: Optional[int] = None
    missing_session_count: Optional[int] = None
    history_gaps_flag: bool = False
    corporate_action_review_flag: bool = False
    price_break_detected_flag: bool = False
    non_eq_series_flag: bool = False

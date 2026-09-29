"""Per-symbol classification and flags (Section 6).

Checked in order, first match wins: FAILED -> INSUFFICIENT_HISTORY ->
STALE -> VALID. FAILED itself (acquisition/parsing/storage failure, or an
unmatched instrument mapping) is decided by the caller before this module
is even consulted -- classify_symbol only ever returns the other three,
since a FAILED symbol has no candle series to classify against a window
at all. Network failure is never classified INSUFFICIENT_HISTORY; missing
data is not stale data (Section 6).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence

from equity_intel.config import PRICE_BREAK_HIGH_RATIO, PRICE_BREAK_LOW_RATIO, REQUIRED_SESSIONS

FAILED = "FAILED"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
STALE = "STALE"
VALID = "VALID"


@dataclass(frozen=True)
class SymbolClassification:
    symbol_data_status: str
    status_reason: Optional[str]
    available_session_count: int
    missing_session_count: int
    history_gaps_flag: bool


def compute_window_sessions(
    calendar_dates: Sequence[str],
    latest_closed_session: str,
    required_sessions: int = REQUIRED_SESSIONS,
) -> List[str]:
    """The trailing `required_sessions` calendar session dates (ISO
    strings) at or before `latest_closed_session`, ascending. Fewer than
    `required_sessions` dates are returned only when the calendar itself
    doesn't have that many sessions at or before that date yet (e.g. very
    early history) -- classify_symbol still correctly reports
    INSUFFICIENT_HISTORY in that case, since available_session_count can
    then never reach required_sessions either.

    `calendar_dates` need not be pre-sorted.
    """
    eligible = sorted(d for d in calendar_dates if d <= latest_closed_session)
    if len(eligible) <= required_sessions:
        return eligible
    return eligible[-required_sessions:]


def classify_symbol(
    *,
    valid_trading_dates: Iterable[str],
    window_sessions: Sequence[str],
    latest_closed_session: str,
    required_sessions: int = REQUIRED_SESSIONS,
) -> SymbolClassification:
    """Classify a symbol that was NOT FAILED (acquisition/mapping
    succeeded) against its trailing window.

    `valid_trading_dates`: ISO date strings of this run's VALID candles
    for the symbol (candle_validation_status == VALID), any order.
    `window_sessions`: this symbol's trailing window, from
    compute_window_sessions -- shared per run since it does not depend on
    any one symbol's data, but passed in explicitly rather than
    recomputed here so every symbol in a run is judged against exactly
    the same window.
    """
    valid_dates = set(valid_trading_dates)
    window = list(window_sessions)

    available = [d for d in window if d in valid_dates]
    available_session_count = len(available)
    missing_session_count = len(window) - available_session_count
    history_gaps_flag = missing_session_count > 0

    if available_session_count < required_sessions:
        return SymbolClassification(
            symbol_data_status=INSUFFICIENT_HISTORY,
            status_reason=(
                f"only {available_session_count} valid candle(s) in the trailing "
                f"{len(window)}-session window (need {required_sessions})"
            ),
            available_session_count=available_session_count,
            missing_session_count=missing_session_count,
            history_gaps_flag=history_gaps_flag,
        )

    latest_valid = max(valid_dates) if valid_dates else None
    if latest_valid is None or latest_valid < latest_closed_session:
        return SymbolClassification(
            symbol_data_status=STALE,
            status_reason=(
                f"latest valid candle ({latest_valid}) is older than "
                f"latest_closed_session ({latest_closed_session})"
            ),
            available_session_count=available_session_count,
            missing_session_count=missing_session_count,
            history_gaps_flag=history_gaps_flag,
        )

    return SymbolClassification(
        symbol_data_status=VALID,
        status_reason=None,
        available_session_count=available_session_count,
        missing_session_count=missing_session_count,
        history_gaps_flag=history_gaps_flag,
    )


def detect_price_break(
    closes_in_date_order: Sequence[Decimal],
    *,
    low_ratio: float = PRICE_BREAK_LOW_RATIO,
    high_ratio: float = PRICE_BREAK_HIGH_RATIO,
) -> bool:
    """True if any consecutive pair of VALID closes (already sorted by
    trading_date ascending) has close[t]/close[t-1] < low_ratio or >
    high_ratio (Section 6). Flag only -- the caller never truncates or
    drops anything because of this; PRICE_BREAK_DETECTED is reported and
    nothing downstream reacts to it automatically.
    """
    for prev, curr in zip(closes_in_date_order, closes_in_date_order[1:]):
        if prev == 0:
            continue  # a non-positive prior close is already CandleValidation's problem, not a break ratio
        ratio = curr / prev
        if ratio < Decimal(str(low_ratio)) or ratio > Decimal(str(high_ratio)):
            return True
    return False


def write_symbol_scan_result(
    conn,
    *,
    scan_run_id: str,
    symbol: str,
    instrument_key: Optional[str],
    isin: Optional[str],
    series: Optional[str],
    company_name: Optional[str],
    sector: Optional[str],
    symbol_data_status: str,
    status_reason: Optional[str],
    available_session_count: Optional[int],
    missing_session_count: Optional[int],
    history_gaps_flag: bool = False,
    corporate_action_review_flag: bool = False,
    price_break_detected_flag: bool = False,
    non_eq_series_flag: bool = False,
) -> None:
    """Insert one symbol_scan_results row. Only ever called while the
    owning scan_run is RUNNING -- schema.py's
    prevent_symbol_scan_result_insert_for_finished_run trigger refuses it
    otherwise.
    """
    conn.execute(
        """
        INSERT INTO symbol_scan_results
            (scan_run_id, symbol, instrument_key, isin, series, company_name, sector,
             symbol_data_status, status_reason, available_session_count, missing_session_count,
             history_gaps_flag, corporate_action_review_flag, price_break_detected_flag, non_eq_series_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_run_id,
            symbol,
            instrument_key,
            isin,
            series,
            company_name,
            sector,
            symbol_data_status,
            status_reason,
            available_session_count,
            missing_session_count,
            int(history_gaps_flag),
            int(corporate_action_review_flag),
            int(price_break_detected_flag),
            int(non_eq_series_flag),
        ),
    )

"""Trading calendar derived from NSE_INDEX|Nifty 500 daily candles.

Per docs/architecture/equity_intel_scanner_v1_spec.md Section 3 (B3-07,
frozen): the benchmark's own daily candles are the authoritative trading
calendar for V1 -- a positive list of actual session dates, not a
computed weekday-minus-holidays filter (a real session has fallen on a
Sunday; see research/b3_live_evidence_resolution_2026-09-26.md Section
2). No NSE holiday file is used in V1 -- every ScanRun records
calendar_verification = "UNVERIFIED_INDEX_ONLY".

Module named trading_calendar, not calendar, to avoid any confusion with
the stdlib calendar module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import List, Optional, Sequence

from equity_intel.config import IST, SESSION_CUTOFF_IST, session_date

BENCHMARK_INSTRUMENT_KEY = "NSE_INDEX|Nifty 500"
CALENDAR_VERIFICATION_UNVERIFIED_INDEX_ONLY = "UNVERIFIED_INDEX_ONLY"

# Recorded as scan_runs.abort_reason when the benchmark index fetch fails,
# is empty, or cannot be parsed (Section 3). Wiring the actual RUNNING ->
# ABORTED transition is scan_run.py's job; this module only raises
# CalendarInvalidError and exposes the reason string for that caller.
CALENDAR_INVALID = "CALENDAR_INVALID"


class CalendarInvalidError(RuntimeError):
    """Raised when the benchmark index fetch fails, is empty, or cannot be
    parsed. Per Section 3, the caller must end the ScanRun ABORTED with
    abort_reason=CALENDAR_INVALID and classify no symbols."""


@dataclass(frozen=True)
class TradingCalendar:
    calendar_source: str
    calendar_verification: str
    calendar_dates: List[str]  # ISO date strings, ascending, the positive session list
    latest_closed_session: str  # ISO date string


def _now_ist(now: Optional[datetime]) -> datetime:
    if now is not None:
        return now
    return datetime.now(IST)


def build_trading_calendar(
    benchmark_candles: Sequence,
    *,
    benchmark_source: str = BENCHMARK_INSTRUMENT_KEY,
    now: Optional[datetime] = None,
) -> TradingCalendar:
    """Build the calendar from already-fetched benchmark candles.

    `benchmark_candles` is a sequence of objects with a `.timestamp`
    (e.g. core.providers.base_provider.HistoricalCandle) -- this function
    does no fetching itself; see fetch_and_build_calendar for that.

    latest_closed_session = the most recent index candle date where
    (date < today) OR (date == today AND now >= SESSION_CUTOFF_IST), per
    Section 3. `now` defaults to the current IST time; pass an explicit
    value for deterministic tests.
    """
    if not benchmark_candles:
        raise CalendarInvalidError("benchmark fetch returned no candles")

    dates = set()
    for candle in benchmark_candles:
        ts = getattr(candle, "timestamp", None)
        if ts is None:
            raise CalendarInvalidError("a benchmark candle is missing a timestamp")
        dates.add(session_date(ts) or ts)

    if not dates:
        raise CalendarInvalidError("benchmark fetch produced no usable session dates")

    current = _now_ist(now)
    today = current.date()
    cutoff_passed = current.time() >= time(SESSION_CUTOFF_IST, 0)

    eligible = [d for d in dates if d < today or (d == today and cutoff_passed)]
    if not eligible:
        raise CalendarInvalidError(
            "no benchmark session date qualifies as the latest closed session as of now"
        )
    latest_closed_session: date = max(eligible)

    return TradingCalendar(
        calendar_source=benchmark_source,
        calendar_verification=CALENDAR_VERIFICATION_UNVERIFIED_INDEX_ONLY,
        calendar_dates=[d.isoformat() for d in sorted(dates)],
        latest_closed_session=latest_closed_session.isoformat(),
    )


def fetch_and_build_calendar(
    provider,
    *,
    start_date: datetime,
    end_date: datetime,
    now: Optional[datetime] = None,
):
    """Fetch the benchmark's daily candles and build the calendar from them.

    Imports fetch_symbol_candles lazily to avoid a module-import cycle
    (acquisition.py has no need to import this module, but keeping the
    import local here keeps the dependency direction obviously one-way).

    Raises:
        CalendarInvalidError: fetch failed or returned no candles.
        equity_intel.scanner.acquisition.AuthFailedError: a 401 -- Section
            9 aborts the whole ScanRun the same way for a calendar fetch
            as for any other vendor call, not just CALENDAR_INVALID.
    """
    from equity_intel.scanner.acquisition import fetch_symbol_candles

    candles, error = fetch_symbol_candles(provider, BENCHMARK_INSTRUMENT_KEY, start_date, end_date)
    if error is not None:
        raise CalendarInvalidError(f"benchmark fetch failed: {error}")
    if not candles:
        raise CalendarInvalidError("benchmark fetch returned no candles")
    return build_trading_calendar(candles, benchmark_source=BENCHMARK_INSTRUMENT_KEY, now=now)

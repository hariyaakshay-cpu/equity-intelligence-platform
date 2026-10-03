"""Recover a latest-session bar that Upstox silently omitted.

Upstox's daily-candle endpoint sometimes drops the newest bar depending on
the length of the requested window (observed 2026-09-30: RELIANCE returned
through 2026-09-28 for 400- and 420-day windows, through 2026-09-29 for 300-
and 450+-day windows). A short recent-window refetch is a cause-independent
repair: it only ever ADDS bars newer than the last one already held.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Optional, Sequence

from equity_intel.config import session_date


def _bar_date(candle) -> date | None:
    return session_date(getattr(candle, "timestamp", None))


def backfill_latest_bars(provider, instrument_key: str, candles: Sequence, expected_last: date | None,
                         now: datetime, *, recent_days: int = 14,
                         before_refetch: Optional[Callable[[], None]] = None) -> tuple[list, bool]:
    """Return (candles, refetched). Refetches only when the newest held bar is
    older than `expected_last`; appends only bars strictly newer than it.
    Any refetch failure leaves `candles` unchanged (the caller's validation
    still sees the gap and reports it)."""
    held = list(candles)
    dates = [d for d in map(_bar_date, held) if d is not None]
    if not dates or expected_last is None or max(dates) >= expected_last:
        return held, False
    last = max(dates)
    if before_refetch is not None:
        before_refetch()  # e.g. rate-limit pacing, only when a request is actually made
    try:
        recent = provider.get_historical_data(instrument_key, "1day", now - timedelta(days=recent_days), now)
    except Exception:
        return held, True
    added = [c for c in recent if (_bar_date(c) is not None and _bar_date(c) > last)]
    return held + added, True

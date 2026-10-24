"""Phase 1 intraday data probe: what does Upstox actually return for 5-minute candles?

Pure analysis lives here (summarize_candles); the network calls live in
scripts/equity_intraday_probe.py. Nothing here writes to any database or
imports a broker/order path. The probe measures, it does not assume: window
limits, bars per session, gaps, zero-volume bars, forming-bar behaviour.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Sequence

IST = timezone(timedelta(hours=5, minutes=30))
BAR_MINUTES = 5
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
EXPECTED_BARS_PER_SESSION = 75  # 09:15 .. 15:25 start times at 5 minutes


def _ist(stamp: datetime) -> datetime:
    return (stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).astimezone(IST)


def summarize_candles(candles: Sequence, now: Optional[datetime] = None) -> dict:
    """Describe a list of HistoricalCandle-like objects (timestamp, open, high, low, close, volume).

    A bar is CLOSED only when its start time + 5 minutes <= now (spec Section 4:
    only closed bars may feed a rule); the report counts bars that are not.
    """
    now = _ist(now or datetime.now(timezone.utc))
    out: dict = {"candle_count": len(candles)}
    stamps = [_ist(c.timestamp) for c in candles if getattr(c, "timestamp", None) is not None]
    out["missing_timestamp"] = len(candles) - len(stamps)
    if not stamps:
        return out
    out["first_bar"], out["last_bar"] = stamps[0].isoformat(), stamps[-1].isoformat()
    out["utc_offsets_seen"] = sorted({s.utcoffset().total_seconds() / 3600 for s in stamps})
    out["duplicate_timestamps"] = sum(n - 1 for n in Counter(stamps).values() if n > 1)
    out["not_monotonic"] = sum(1 for a, b in zip(stamps, stamps[1:]) if b <= a)
    out["not_on_5min_grid"] = sum(1 for s in stamps if s.minute % BAR_MINUTES or s.second)
    out["outside_session"] = sum(1 for s in stamps if not (SESSION_OPEN <= s.time() < SESSION_CLOSE))
    out["forming_bars"] = sum(1 for s in stamps if s + timedelta(minutes=BAR_MINUTES) > now)
    out["bad_ohlc"] = sum(1 for c in candles if None in (c.open, c.high, c.low, c.close)
                          or c.high < max(c.open, c.close, c.low) or c.low > min(c.open, c.close, c.high))
    out["zero_or_missing_volume"] = sum(1 for c in candles if not c.volume)
    per_day: dict = defaultdict(int)
    for s in stamps:
        per_day[s.date().isoformat()] += 1
    counts = sorted(per_day.values())
    out["sessions"] = len(per_day)
    out["bars_per_session"] = {"min": counts[0], "median": counts[len(counts) // 2], "max": counts[-1],
                               "expected": EXPECTED_BARS_PER_SESSION,
                               "sessions_short_of_expected": sum(1 for n in counts if n < EXPECTED_BARS_PER_SESSION)}
    out["short_sessions"] = {d: n for d, n in sorted(per_day.items()) if n < EXPECTED_BARS_PER_SESSION}
    return out


def last_weekday_on_or_before(day: datetime) -> datetime:
    """Weekday approximation only: NSE holidays are NOT known here (spec Section 4 requires the verified calendar)."""
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day

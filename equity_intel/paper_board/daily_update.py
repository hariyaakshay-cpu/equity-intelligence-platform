"""Pure helpers for the incremental data/daily_live update and the board's session calendar. No I/O."""
from __future__ import annotations

from datetime import date, timedelta

OVERLAP_DAYS = 7          # re-fetch this many calendar days before the last stored date (late corrections)


def fetch_from(last: date) -> date:
    return last - timedelta(days=OVERLAP_DAYS)


def merge(existing: dict, fetched: dict) -> dict:
    """date-iso -> (o, h, l, c, v). Fetched rows replace stored rows on the same date; older rows are kept."""
    out = dict(existing)
    out.update(fetched)
    return dict(sorted(out.items()))


def session_calendar(known: list[date], today: date) -> tuple[list[date], list[date]]:
    """Trading sessions up to today for the board.

    known: dates in the NIFTY 500 index file. Weekdays after its last date and
    before today are assumed to be sessions whose prices are not loaded yet
    (so a stale file is detected instead of silently treated as current).
    Returns (sessions ending with today, inferred dates).
    """
    past = sorted(d for d in known if d < today)
    inferred, d = [], (past[-1] + timedelta(days=1)) if past else today
    while d < today:
        if d.weekday() < 5:
            inferred.append(d)
        d += timedelta(days=1)
    return past + inferred + [today], inferred

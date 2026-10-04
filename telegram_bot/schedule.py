"""Decide whether a scheduled digest should run today.

Uses the verified NSE calendar (research/ml/calendar). Dates after the end of
the calendar fall back to Mon-Fri, which is approximate (holidays unknown).
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

CALENDAR_PATH = Path(__file__).resolve().parents[1] / "research" / "ml" / "calendar" / "nse_equity_calendar_v1.csv"


def is_session_day(day: date, calendar_path: Path = CALENDAR_PATH) -> tuple[bool, str]:
    """(is_session, basis). Basis is 'calendar' or 'weekday-fallback'."""
    key = day.isoformat()
    try:
        with open(calendar_path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["date"] == key:
                    return row["is_session"] == "1", "calendar"
    except OSError:
        pass
    return day.weekday() < 5, "weekday-fallback"

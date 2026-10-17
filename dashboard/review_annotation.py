"""Snapshot Audit: a facts-only note listing review-file entries dated between the two compared runs.

The window is the half-open range (older run's scan_runs.started_at date, newer run's started_at date], so an entry
dated the older run's start day is excluded and one dated the newer run's start day is included. Both runs are
ScanRuns (the page's layer). The note states what the review file lists and nothing about why any bar differs.

A file that is empty, unavailable, or has no entry in the window yields None: nothing is shown, and the page never
says "0 issues". The file is read through review_file.read_review_file; demo mode never reads it. Like queries.py
this module never imports sqlite3.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from dashboard import review_file, stock_detail

SENTENCE = "listed in the review file; this page does not say it explains any difference"
WINDOW_NOTE = ("window: effective_date after the older run's start date and on or before the newer run's start date "
               "(both from scan_runs.started_at)")


def _day(value) -> Optional[date]:
    """The calendar date of an ISO timestamp or date (first 10 characters, no timezone conversion), else None."""
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def build(body: dict, demo: bool, symbol: Optional[str] = None) -> Optional[dict]:
    """The annotation for a Snapshot Audit payload (page or drill-down), or None when there is nothing to show.

    `body` is a snapshot_audit.build / build_symbol payload (base_run is the older run, other_run the newer).
    `symbol` restricts the entries to one symbol (the drill-down page).
    """
    if demo or body.get("comparison_available") is not True:
        return None
    older, newer = body["base_run"], body["other_run"]
    start, end = _day(older["started_at"]), _day(newer["started_at"])
    if start is None or end is None:
        return None
    state = review_file.read_review_file(stock_detail.review_csv_path(), None)
    if state["file_state"] != "has_entries":
        return None
    rows, skipped = [], 0
    for entry in state["entries"]:
        if symbol is not None and entry.symbol != symbol:
            continue
        effective = _day(entry.effective_date) if len(entry.effective_date) == 10 else None
        if effective is None:
            skipped += 1
        elif start < effective <= end:
            rows.append({"symbol": entry.symbol, "event_type": entry.event_type, "effective_date": entry.effective_date})
    if not rows:
        return None
    rows.sort(key=lambda r: (r["effective_date"], r["symbol"], r["event_type"]))
    return {
        "layer": "ScanRun",
        "older_started_at": older["started_at"],
        "newer_started_at": newer["started_at"],
        "sentence": SENTENCE,
        "window_note": WINDOW_NOTE,
        "rows": rows,
        "skipped_unparseable": skipped,
    }

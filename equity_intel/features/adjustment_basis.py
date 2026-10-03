"""Stale adjustment-basis detection for stored acquisition runs.

Upstox daily candles are adjusted for splits/bonuses *at fetch time*
(research/upstox_adjustment_basis_check_2026-10-03.md). A stored acquisition
run therefore keeps the price basis of the day it was fetched: if a corporate
action takes effect on or after that day, the stored series is on the pre-event
basis, and `breaks.py` cannot see it (the event is not in the data yet).

The only corporate-action source is the manual review CSV
(data/reference/corporate_action_review.csv). An entry is a post-fetch event for
a run when

    fetch_date_ist <= effective_date <= scan_date_ist

The fetch day itself counts: whether Upstox had applied a same-day event when
the run fetched is unknown, so the check errs toward flagging. It clears only
when a run is re-acquired on a later date. `review_state` and `event_type` are
deliberately ignored: any action effective after the fetch means the stored
series predates it. Flag only; nothing stored is mutated.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Optional

from equity_intel.config import IST
from equity_intel.scanner.corporate_actions import CorporateActionReview, ReviewEntry

ADJUSTMENT_BASIS_STALE = "ADJUSTMENT_BASIS_STALE"


def ist_date(stamp: str | datetime) -> date:
    """Calendar date in IST of an ISO timestamp. Naive timestamps are UTC."""
    moment = datetime.fromisoformat(stamp) if isinstance(stamp, str) else stamp
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(IST).date()


def post_fetch_events(review: CorporateActionReview, symbol: str, fetch_date: date, scan_date: date) -> list[ReviewEntry]:
    """Review entries for `symbol` effective in [fetch_date, scan_date], oldest first."""
    hits = []
    for entry in review.entries:
        if entry.symbol != symbol:
            continue
        try:
            effective = date.fromisoformat(entry.effective_date)
        except ValueError:
            continue  # unparseable dates are the scanner's concern (Section 7), not a basis signal
        if fetch_date <= effective <= scan_date:
            hits.append(entry)
    return sorted(hits, key=lambda e: e.effective_date)


def stale_basis_reason(events: Iterable[ReviewEntry], acquisition_run_id: str, fetch_date: date) -> Optional[str]:
    events = list(events)
    if not events:
        return None
    described = ", ".join(f"{e.event_type} effective {e.effective_date}" for e in events)
    return (f"{ADJUSTMENT_BASIS_STALE}: acquisition run {acquisition_run_id} fetched {fetch_date.isoformat()} (IST) "
            f"predates {described}; re-run scripts/equity_data_acquisition.py")

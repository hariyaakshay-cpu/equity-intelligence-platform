"""Candidate / watchlist record shapes.

These describe what a row would look like IF a candidate or watchlist
decision had been made -- they do not make that decision. `rank` and
`is_candidate`/`is_watchlisted` are Optional and are never populated by
this scaffold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from equity_intel.contracts.state import ScanState


@dataclass(frozen=True)
class Candidate:
    instrument_id: str
    scan_id: str
    state: ScanState
    composite: Optional[int] = None
    rank: Optional[int] = None


@dataclass(frozen=True)
class WatchlistEntry:
    """A row of the eventual paper_watchlist persistence store.

    Per the B1 freeze-policy exception, `paper_watchlist` is the ONLY
    permitted handoff out of this package, and a WatchlistEntry is not and
    must never become an order, position, or execution request. There is no
    broker/order/OMS-identifying field on this record.
    """

    instrument_id: str
    scan_id: str
    rank: Optional[int] = None
    composite: Optional[int] = None
    score_version: Optional[str] = None

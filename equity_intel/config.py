"""Shared, non-scoring configuration constants for equity_intel.

Nothing here is a B2 scoring band, threshold, or cutoff (those remain
unresolved governance decisions -- see equity_intel/contracts/scoring.py
and equity_intel/scoring/interfaces.py). This module holds operational
constants that multiple independent parts of the package must agree on
bit-for-bit, so they are defined exactly once and imported everywhere,
never re-declared with a locally-invented value.
"""
from __future__ import annotations

# The hour (IST, 24h clock) after which a weekday's trading session is
# considered closed, for freshness/staleness purposes (e.g. the Phase 4
# dashboard's OUTDATED check in dashboard/queries.py). The scanner's own
# session/calendar handling (once implemented) must import this same
# constant rather than hardcode its own cutoff hour -- a scanner that
# decided "closed" at a different hour than the dashboard's freshness
# check would silently disagree with it.
SESSION_CUTOFF_IST = 18

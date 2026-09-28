"""Shared, non-scoring configuration constants for equity_intel.

Nothing here is a B2 scoring band, threshold, or cutoff (those remain
unresolved governance decisions -- see equity_intel/contracts/scoring.py
and equity_intel/scoring/interfaces.py). This module holds operational
constants that multiple independent parts of the package must agree on
bit-for-bit, so they are defined exactly once and imported everywhere,
never re-declared with a locally-invented value.
"""
from __future__ import annotations

from datetime import timedelta, timezone

# The hour (IST, 24h clock) after which a weekday's trading session is
# considered closed, for freshness/staleness purposes (e.g. the Phase 4
# dashboard's OUTDATED check in dashboard/queries.py, and the Phase 2
# scanner's own calendar/latest_closed_session logic in
# equity_intel/scanner/trading_calendar.py). Every part of this package
# that needs "is today's session closed yet" imports this same constant
# rather than hardcoding its own cutoff hour -- two callers deciding
# "closed" at different hours would silently disagree with each other.
SESSION_CUTOFF_IST = 18

# IST (UTC+5:30, no DST) as a fixed tzinfo, for code that needs an
# aware IST datetime (e.g. writing started_at/finished_at/fetched_at_ist
# with an explicit "+05:30" offset -- see
# docs/architecture/equity_intel_scanner_v1_spec.md Section 8/9).
IST = timezone(timedelta(hours=5, minutes=30))

# How many *calendar* days back the scanner requests from the price
# vendor for each symbol (and for the benchmark calendar fetch), per scan
# run. Not a governance threshold: it only has to be comfortably larger
# than REQUIRED_SESSIONS (252) trading sessions' worth of calendar time,
# so that a healthy symbol's fetch window contains at least 252 valid
# candles after accounting for weekends and holidays (252 trading days is
# roughly 353 calendar days at a 5/7 trading-day density; this adds
# further margin for holidays). Symbol classification itself (Phase 3)
# is REQUIRED_SESSIONS, not this constant.
PRICE_FETCH_LOOKBACK_DAYS = 400

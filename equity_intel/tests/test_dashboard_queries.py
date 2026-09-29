"""Tests for the pure calendar/staleness logic in dashboard/queries.py.

2026-09-25 is a Friday and 2026-09-28 is the following Monday (verified:
2026-01-01 is a Thursday, so day-of-year 271 = 2026-09-28 is
(271-1) % 7 = 4 weekdays after Thursday = Monday). These fixed dates make
the tests deterministic regardless of when they're actually run, instead
of depending on the real host clock.
"""
from datetime import datetime, timedelta

from dashboard import queries
from equity_intel.config import SESSION_CUTOFF_IST

FRIDAY = "2026-09-25"
MONDAY = "2026-09-28"


def test_friday_run_viewed_monday_morning_before_cutoff_is_not_outdated():
    run = {"latest_closed_session": FRIDAY}
    now = datetime(2026, 9, 28, 10, 0, 0)  # Monday 10:00 IST, before the 18:00 cutoff
    assert queries.is_outdated(run, now) is False


def test_friday_run_viewed_monday_evening_after_cutoff_is_outdated():
    run = {"latest_closed_session": FRIDAY}
    now = datetime(2026, 9, 28, 19, 0, 0)  # Monday 19:00 IST, after the 18:00 cutoff
    assert queries.is_outdated(run, now) is True


def test_run_viewed_same_day_before_cutoff_is_not_outdated():
    run = {"latest_closed_session": MONDAY}
    now = datetime(2026, 9, 28, 10, 0, 0)  # same Monday, before its own cutoff
    assert queries.is_outdated(run, now) is False


def test_run_viewed_same_day_after_cutoff_is_not_outdated_either():
    # Once today's own cutoff has passed, today's session is exactly the
    # expected one -- a run reporting *today's* close is still current.
    run = {"latest_closed_session": MONDAY}
    now = datetime(2026, 9, 28, 19, 0, 0)
    assert queries.is_outdated(run, now) is False


def test_missing_latest_closed_session_is_treated_as_outdated():
    assert queries.is_outdated({"latest_closed_session": None}) is True
    assert queries.is_outdated({}) is True


def test_expected_latest_session_on_a_weekday_morning_is_the_prior_friday():
    now = datetime(2026, 9, 28, 10, 0, 0)  # Monday, before cutoff
    assert queries.expected_latest_session(now).isoformat() == FRIDAY


def test_expected_latest_session_on_a_weekday_evening_is_today():
    now = datetime(2026, 9, 28, 19, 0, 0)  # Monday, after cutoff
    assert queries.expected_latest_session(now).isoformat() == MONDAY


def test_expected_latest_session_on_a_weekend_is_the_prior_friday():
    saturday = datetime(2026, 9, 26, 12, 0, 0)
    sunday = datetime(2026, 9, 27, 12, 0, 0)
    assert queries.expected_latest_session(saturday).isoformat() == FRIDAY
    assert queries.expected_latest_session(sunday).isoformat() == FRIDAY


def test_expected_latest_session_uses_the_shared_session_cutoff_constant():
    # The dashboard's cutoff and equity_intel.config.SESSION_CUTOFF_IST
    # must be the same value bit-for-bit -- any future scanner code that
    # decides "session closed" must agree with this dashboard, not define
    # its own competing cutoff hour.
    assert SESSION_CUTOFF_IST == 18
    just_before = datetime(2026, 9, 28, SESSION_CUTOFF_IST, 0, 0) - timedelta(minutes=1)
    just_after = datetime(2026, 9, 28, SESSION_CUTOFF_IST, 0, 0) + timedelta(minutes=1)
    assert queries.expected_latest_session(just_before).isoformat() == FRIDAY
    assert queries.expected_latest_session(just_after).isoformat() == MONDAY

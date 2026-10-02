"""Tests for equity_intel.scanner.classification."""
from decimal import Decimal

import pytest

from equity_intel.persistence import connection, db_path_guard
from equity_intel.scanner.classification import (
    INSUFFICIENT_HISTORY,
    STALE,
    VALID,
    classify_symbol,
    compute_window_sessions,
    detect_price_break,
    write_symbol_scan_result,
)


def _sessions(n, start="2026-01-01"):
    # n consecutive ISO calendar dates starting at `start` -- good enough
    # for window-size tests; classify_symbol never interprets gaps between
    # them, it only checks membership.
    from datetime import date, timedelta

    d = date.fromisoformat(start)
    return [(d + timedelta(days=i)).isoformat() for i in range(n)]


def test_compute_window_sessions_returns_trailing_n_at_or_before_cutoff():
    dates = _sessions(10)  # 2026-01-01 .. 2026-01-10, indices 0..9
    # "2026-01-08" is dates[7]; eligible (<= cutoff) is dates[0:8], and the
    # trailing 5 of those are dates[3:8].
    window = compute_window_sessions(dates, latest_closed_session="2026-01-08", required_sessions=5)
    assert window == dates[3:8]
    assert window[-1] == "2026-01-08"
    assert len(window) == 5


def test_compute_window_sessions_excludes_dates_after_the_cutoff():
    dates = _sessions(5)
    window = compute_window_sessions(dates, latest_closed_session=dates[2], required_sessions=10)
    assert window == dates[:3]


def test_compute_window_sessions_returns_fewer_than_required_when_calendar_is_short():
    dates = _sessions(3)
    window = compute_window_sessions(dates, latest_closed_session=dates[-1], required_sessions=252)
    assert window == dates


def test_compute_window_sessions_works_with_unsorted_input():
    dates = _sessions(5)
    window = compute_window_sessions(list(reversed(dates)), latest_closed_session=dates[-1], required_sessions=3)
    assert window == dates[-3:]


def test_classify_symbol_insufficient_history_when_fewer_than_required_valid_candles():
    window = _sessions(10)
    valid_dates = window[:4]  # only 4 of 10 sessions have a valid candle
    result = classify_symbol(
        valid_trading_dates=valid_dates, window_sessions=window, latest_closed_session=window[-1], required_sessions=5
    )
    assert result.symbol_data_status == INSUFFICIENT_HISTORY
    assert "4" in result.status_reason
    assert result.available_session_count == 4
    assert result.missing_session_count == 6
    assert result.history_gaps_flag is True


def test_classify_symbol_stale_when_latest_valid_candle_is_older_than_latest_closed_session():
    window = _sessions(6)
    # Enough valid candles to clear INSUFFICIENT_HISTORY, but none as recent
    # as the last session in the window.
    valid_dates = window[:5]
    result = classify_symbol(
        valid_trading_dates=valid_dates, window_sessions=window, latest_closed_session=window[-1], required_sessions=5
    )
    assert result.symbol_data_status == STALE
    assert result.available_session_count == 5
    assert result.missing_session_count == 1
    assert result.history_gaps_flag is True


def test_classify_symbol_valid_when_fresh_and_sufficient():
    window = _sessions(5)
    result = classify_symbol(
        valid_trading_dates=window, window_sessions=window, latest_closed_session=window[-1], required_sessions=5
    )
    assert result.symbol_data_status == VALID
    assert result.status_reason is None
    assert result.available_session_count == 5
    assert result.missing_session_count == 0
    assert result.history_gaps_flag is False


def test_classify_symbol_valid_can_still_carry_history_gaps():
    # 5 of 6 sessions have a valid candle, but the most recent one does --
    # so this is VALID (not STALE, not INSUFFICIENT_HISTORY given
    # required_sessions=5) while still missing one session in the window.
    window = _sessions(6)
    valid_dates = [window[0], window[1], window[2], window[3], window[5]]  # missing window[4]
    result = classify_symbol(
        valid_trading_dates=valid_dates, window_sessions=window, latest_closed_session=window[-1], required_sessions=5
    )
    assert result.symbol_data_status == VALID
    assert result.history_gaps_flag is True
    assert result.missing_session_count == 1


def test_classify_symbol_with_no_valid_candles_at_all_is_insufficient_history_not_stale():
    window = _sessions(5)
    result = classify_symbol(
        valid_trading_dates=[], window_sessions=window, latest_closed_session=window[-1], required_sessions=5
    )
    # Network failure is never classified INSUFFICIENT_HISTORY... but zero
    # valid candles from a symbol that DID resolve and DID get fetched (just
    # produced no valid rows) is exactly the "fewer than required" case --
    # first match wins, and 0 < 5.
    assert result.symbol_data_status == INSUFFICIENT_HISTORY


def test_detect_price_break_flags_a_halving():
    closes = [Decimal("100.00"), Decimal("101.00"), Decimal("40.00")]  # 40/101 < 0.5
    assert detect_price_break(closes) is True


def test_detect_price_break_flags_a_doubling():
    closes = [Decimal("100.00"), Decimal("250.00")]  # 250/100 > 2.0
    assert detect_price_break(closes) is True


def test_detect_price_break_does_not_flag_normal_moves():
    closes = [Decimal("100.00"), Decimal("101.50"), Decimal("99.00"), Decimal("103.25")]
    assert detect_price_break(closes) is False


def test_detect_price_break_boundary_ratios_are_not_flagged():
    # Exactly 0.5 and exactly 2.0 are the boundary, not beyond it (spec: <
    # 0.5 or > 2.0, strict inequalities).
    closes = [Decimal("100.00"), Decimal("50.00"), Decimal("100.00")]
    assert detect_price_break(closes) is False


def test_detect_price_break_empty_or_single_close_is_never_flagged():
    assert detect_price_break([]) is False
    assert detect_price_break([Decimal("100.00")]) is False


@pytest.fixture
def conn(monkeypatch, tmp_path):
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    c = connection.get_connection(path)
    connection.initialize_schema(c)
    c.execute(
        "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
        "VALUES ('r1', '2026-09-28T09:00:00+05:30', 'RUNNING', 'BLOCKED_B2')"
    )
    c.commit()
    try:
        yield c
    finally:
        c.close()


def test_write_symbol_scan_result_persists_all_fields(conn):
    write_symbol_scan_result(
        conn,
        scan_run_id="r1",
        symbol="TCS",
        instrument_key="NSE_EQ|INE1",
        isin="INE1",
        series="EQ",
        company_name="Tata Consultancy Services",
        sector="IT",
        symbol_data_status=VALID,
        status_reason=None,
        available_session_count=252,
        missing_session_count=0,
        history_gaps_flag=False,
        corporate_action_review_flag=True,
        price_break_detected_flag=False,
        non_eq_series_flag=False,
    )
    conn.commit()
    row = conn.execute(
        "SELECT symbol_data_status, corporate_action_review_flag, non_eq_series_flag "
        "FROM symbol_scan_results WHERE scan_run_id = 'r1' AND symbol = 'TCS'"
    ).fetchone()
    assert row[0] == VALID
    assert row[1] == 1
    assert row[2] == 0

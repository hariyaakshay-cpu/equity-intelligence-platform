"""Tests for equity_intel.scanner.scan_run."""
import json
import sqlite3

import pytest

from equity_intel.persistence import connection, db_path_guard
from equity_intel.scanner import scan_run


@pytest.fixture
def conn(monkeypatch, tmp_path):
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    c = connection.get_connection(path)
    connection.initialize_schema(c)
    try:
        yield c
    finally:
        c.close()


def test_start_scan_run_inserts_a_running_row(conn):
    scan_run.start_scan_run(conn, run_id="r1", requested_symbols=5, price_source="upstox")
    row = conn.execute(
        "SELECT status, requested_symbols, price_source, scoring_status FROM scan_runs WHERE run_id = 'r1'"
    ).fetchone()
    assert row[0] == "RUNNING"
    assert row[1] == 5
    assert row[2] == "upstox"
    assert row[3] == "BLOCKED_B2"


def test_start_scan_run_persists_symbols_filter_json(conn):
    scan_run.start_scan_run(conn, run_id="smoke", requested_symbols=2, symbols_filter=["TCS", "INFY"])
    row = conn.execute("SELECT symbols_filter_json FROM scan_runs WHERE run_id = 'smoke'").fetchone()
    assert json.loads(row[0]) == ["INFY", "TCS"]  # sorted for determinism


def test_start_scan_run_leaves_symbols_filter_json_null_for_a_full_run(conn):
    scan_run.start_scan_run(conn, run_id="full", requested_symbols=500)
    row = conn.execute("SELECT symbols_filter_json FROM scan_runs WHERE run_id = 'full'").fetchone()
    assert row[0] is None


def test_start_scan_run_marks_a_leftover_running_row_interrupted(conn):
    scan_run.start_scan_run(conn, run_id="old", requested_symbols=3)
    # "old" is still RUNNING -- simulating a process that died mid-scan.
    scan_run.start_scan_run(conn, run_id="new", requested_symbols=5)

    old_row = conn.execute("SELECT status, abort_reason FROM scan_runs WHERE run_id = 'old'").fetchone()
    assert old_row[0] == "ABORTED"
    assert old_row[1] == scan_run.INTERRUPTED

    new_row = conn.execute("SELECT status FROM scan_runs WHERE run_id = 'new'").fetchone()
    assert new_row[0] == "RUNNING"


def test_mark_stale_running_as_interrupted_returns_count(conn):
    scan_run.start_scan_run(conn, run_id="a", requested_symbols=1)
    conn.execute("INSERT INTO scan_runs (run_id, started_at, status, scoring_status) VALUES ('b', '2026-01-01T00:00:00+05:30', 'RUNNING', 'BLOCKED_B2')")
    conn.commit()
    count = scan_run.mark_stale_running_as_interrupted(conn)
    assert count == 2
    statuses = {row[0] for row in conn.execute("SELECT status FROM scan_runs").fetchall()}
    assert statuses == {"ABORTED"}


def test_abort_scan_run_sets_aborted_status_and_reason(conn):
    scan_run.start_scan_run(conn, run_id="r1", requested_symbols=5)
    scan_run.abort_scan_run(conn, run_id="r1", abort_reason="CALENDAR_INVALID", errors=["benchmark fetch empty"])
    row = conn.execute("SELECT status, abort_reason, errors_json, finished_at FROM scan_runs WHERE run_id = 'r1'").fetchone()
    assert row[0] == "ABORTED"
    assert row[1] == "CALENDAR_INVALID"
    assert "benchmark fetch empty" in row[2]
    assert row[3] is not None


def test_abort_scan_run_is_frozen_afterward(conn):
    scan_run.start_scan_run(conn, run_id="r1", requested_symbols=5)
    scan_run.abort_scan_run(conn, run_id="r1", abort_reason="AUTH_FAILED")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE scan_runs SET requested_symbols = 99 WHERE run_id = 'r1'")


def test_complete_scan_run_sets_complete_and_required_fields(conn):
    scan_run.start_scan_run(conn, run_id="r1", requested_symbols=2)
    scan_run.complete_scan_run(
        conn,
        run_id="r1",
        universe_version="abc",
        corporate_action_review_version="def",
        benchmark="NSE_INDEX|Nifty 500",
        calendar_source="NSE_INDEX|Nifty 500",
        calendar_verification="UNVERIFIED_INDEX_ONLY",
        latest_closed_session="2026-09-25",
        calendar_dates=["2026-09-24", "2026-09-25"],
        successful_symbols=2,
        failed_symbols=0,
        status_counts={"VALID": 2},
        flag_counts={"HISTORY_GAPS": 0},
        excluded_symbols=[{"symbol": "DUMMYHEG", "reason": "DUMMY_SYMBOL"}],
    )
    row = conn.execute(
        "SELECT status, universe_version, corporate_action_review_version, successful_symbols, "
        "status_counts_json, excluded_symbols_json FROM scan_runs WHERE run_id = 'r1'"
    ).fetchone()
    assert row[0] == "COMPLETE"
    assert row[1] == "abc"
    assert row[2] == "def"
    assert row[3] == 2
    assert "VALID" in row[4]
    assert "DUMMYHEG" in row[5]


def test_complete_scan_run_without_universe_version_violates_check_constraint(conn):
    scan_run.start_scan_run(conn, run_id="r1", requested_symbols=1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE scan_runs SET status = 'COMPLETE', finished_at = '2026-09-28T18:00:00+05:30' WHERE run_id = 'r1'"
        )

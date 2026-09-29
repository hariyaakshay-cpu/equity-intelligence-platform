"""DB-level enforcement tests for schema.py -- CHECK constraints and the
price_fetch_snapshots append-only triggers.

Always against an in-memory (":memory:") SQLite connection: never
data/equity_intel.db.
"""
import sqlite3

import pytest

from equity_intel.persistence.schema import SCHEMA_STATEMENTS


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    try:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()
        yield connection
    finally:
        connection.close()


def _insert_scan_run(
    conn,
    run_id="r1",
    status="RUNNING",
    scoring_status="BLOCKED_B2",
    universe_version=None,
    corporate_action_review_version=None,
):
    conn.execute(
        """
        INSERT INTO scan_runs
            (run_id, started_at, status, scoring_status, universe_version, corporate_action_review_version)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, "2026-09-27T00:00:00", status, scoring_status, universe_version, corporate_action_review_version),
    )
    conn.commit()


def _insert_snapshot(conn, scan_run_id="r1", symbol="TCS"):
    conn.execute(
        """
        INSERT INTO price_fetch_snapshots
            (scan_run_id, symbol, trading_date, source, fetched_at_ist, content_hash, candle_validation_status)
        VALUES (?, ?, '2026-09-25', 'upstox', '2026-09-27T18:05:00+05:30', 'deadbeef', 'VALID')
        """,
        (scan_run_id, symbol),
    )
    conn.commit()


def _abort(conn, run_id="r1"):
    conn.execute(
        "UPDATE scan_runs SET status = 'ABORTED' WHERE run_id = ?",
        (run_id,),
    )
    conn.commit()


def test_scan_run_status_check_accepts_the_three_lifecycle_values(conn):
    # A scan_run is always created RUNNING (see the insert-time trigger
    # tests below) -- COMPLETE and ABORTED are reached only via UPDATE.
    _insert_scan_run(conn, run_id="r-RUNNING")

    _insert_scan_run(
        conn,
        run_id="r-COMPLETE",
        universe_version="csv-hash",
        corporate_action_review_version="review-csv-hash",
    )
    _complete(conn, run_id="r-COMPLETE")

    _insert_scan_run(conn, run_id="r-ABORTED")
    _abort(conn, run_id="r-ABORTED")


def test_scan_run_status_check_rejects_anything_else(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _insert_scan_run(conn, status="FAILED")


def test_scan_run_scoring_status_check_rejects_anything_but_blocked_b2(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _insert_scan_run(conn, scoring_status="SCORED")


def test_running_or_aborted_scan_run_does_not_require_either_version(conn):
    # Per docs/architecture/equity_intel_scanner_v1_spec.md Section 9: only
    # COMPLETE requires both provenance hashes -- a RUNNING or ABORTED run
    # may not have reached universe/review-list loading at all.
    _insert_scan_run(conn, run_id="r-running")
    _insert_scan_run(conn, run_id="r-aborted")
    _abort(conn, run_id="r-aborted")


def test_complete_scan_run_requires_universe_version(conn):
    _insert_scan_run(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE scan_runs SET status = 'COMPLETE', corporate_action_review_version = 'c' "
            "WHERE run_id = 'r1'"
        )


def test_complete_scan_run_requires_corporate_action_review_version(conn):
    _insert_scan_run(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE scan_runs SET status = 'COMPLETE', universe_version = 'u' "
            "WHERE run_id = 'r1'"
        )


def test_complete_scan_run_with_both_versions_set_succeeds(conn):
    _insert_scan_run(conn, run_id="r1")
    _complete(conn, run_id="r1")
    row = conn.execute("SELECT status FROM scan_runs WHERE run_id = 'r1'").fetchone()
    assert row[0] == "COMPLETE"


def test_symbol_data_status_check_accepts_the_four_governed_values(conn):
    _insert_scan_run(conn)
    for i, status in enumerate(("VALID", "INSUFFICIENT_HISTORY", "STALE", "FAILED")):
        conn.execute(
            "INSERT INTO symbol_scan_results (scan_run_id, symbol, symbol_data_status) VALUES ('r1', ?, ?)",
            (f"SYM{i}", status),
        )
    conn.commit()


def test_symbol_data_status_check_rejects_anything_else(conn):
    _insert_scan_run(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO symbol_scan_results (scan_run_id, symbol, symbol_data_status) VALUES ('r1', 'X', 'BOGUS')"
        )


def test_candle_validation_status_check_rejects_anything_but_valid_or_invalid(conn):
    _insert_scan_run(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO price_fetch_snapshots
                (scan_run_id, symbol, trading_date, source, fetched_at_ist, content_hash, candle_validation_status)
            VALUES ('r1', 'X', '2026-09-25', 'upstox', 't', 'hash', 'MAYBE')
            """
        )


def test_price_fetch_snapshot_update_is_blocked_by_trigger(conn):
    _insert_scan_run(conn)
    _insert_snapshot(conn)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE price_fetch_snapshots SET close = '999.00' WHERE scan_run_id = 'r1'")


def test_price_fetch_snapshot_delete_is_blocked_by_trigger(conn):
    _insert_scan_run(conn)
    _insert_snapshot(conn)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM price_fetch_snapshots WHERE scan_run_id = 'r1'")
    row = conn.execute("SELECT COUNT(*) FROM price_fetch_snapshots").fetchone()
    assert row[0] == 1


def test_a_rerun_appends_a_new_row_rather_than_touching_the_first(conn):
    _insert_scan_run(conn, run_id="r1")
    _insert_scan_run(conn, run_id="r2")
    _insert_snapshot(conn, scan_run_id="r1")
    _insert_snapshot(conn, scan_run_id="r2")
    count = conn.execute("SELECT COUNT(*) FROM price_fetch_snapshots").fetchone()[0]
    assert count == 2


def _complete(conn, run_id="r1"):
    conn.execute(
        "UPDATE scan_runs SET status = 'COMPLETE', universe_version = 'u', "
        "corporate_action_review_version = 'c' WHERE run_id = ?",
        (run_id,),
    )
    conn.commit()


def test_a_completed_scan_run_can_never_be_reverted_to_running(conn):
    _insert_scan_run(conn, run_id="r1")
    _complete(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError, match="never be updated"):
        conn.execute("UPDATE scan_runs SET status = 'RUNNING' WHERE run_id = 'r1'")


def test_a_scan_run_row_is_never_deleted(conn):
    _insert_scan_run(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError, match="never deleted"):
        conn.execute("DELETE FROM scan_runs WHERE run_id = 'r1'")


def test_a_normal_running_to_complete_transition_still_works(conn):
    _insert_scan_run(conn, run_id="r1")
    _complete(conn, run_id="r1")
    row = conn.execute("SELECT status FROM scan_runs WHERE run_id = 'r1'").fetchone()
    assert row[0] == "COMPLETE"


def test_a_normal_running_to_aborted_transition_still_works(conn):
    _insert_scan_run(conn, run_id="r1")
    _abort(conn, run_id="r1")
    row = conn.execute("SELECT status FROM scan_runs WHERE run_id = 'r1'").fetchone()
    assert row[0] == "ABORTED"


def test_inserting_a_scan_run_as_complete_is_blocked(conn):
    with pytest.raises(sqlite3.IntegrityError, match="must be created as RUNNING"):
        _insert_scan_run(
            conn,
            status="COMPLETE",
            universe_version="csv-hash",
            corporate_action_review_version="review-csv-hash",
        )


def test_inserting_a_scan_run_as_aborted_is_blocked(conn):
    with pytest.raises(sqlite3.IntegrityError, match="must be created as RUNNING"):
        _insert_scan_run(conn, status="ABORTED")


def test_price_fetch_snapshot_insert_into_a_completed_run_is_blocked(conn):
    _insert_scan_run(conn, run_id="r1")
    _complete(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError, match="only be written while"):
        _insert_snapshot(conn, scan_run_id="r1")


def test_inserting_a_symbol_result_into_a_completed_run_is_blocked(conn):
    _insert_scan_run(conn, run_id="r1")
    _complete(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError, match="only be written while"):
        conn.execute(
            "INSERT INTO symbol_scan_results (scan_run_id, symbol, symbol_data_status) VALUES ('r1', 'TCS', 'VALID')"
        )


def test_editing_a_symbol_result_of_a_completed_run_is_blocked(conn):
    _insert_scan_run(conn, run_id="r1")
    conn.execute(
        "INSERT INTO symbol_scan_results (scan_run_id, symbol, symbol_data_status) VALUES ('r1', 'TCS', 'VALID')"
    )
    conn.commit()
    _complete(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError, match="only be modified while"):
        conn.execute(
            "UPDATE symbol_scan_results SET symbol_data_status = 'FAILED' WHERE scan_run_id = 'r1' AND symbol = 'TCS'"
        )


def test_deleting_a_symbol_result_of_a_completed_run_is_blocked(conn):
    _insert_scan_run(conn, run_id="r1")
    conn.execute(
        "INSERT INTO symbol_scan_results (scan_run_id, symbol, symbol_data_status) VALUES ('r1', 'TCS', 'VALID')"
    )
    conn.commit()
    _complete(conn, run_id="r1")
    with pytest.raises(sqlite3.IntegrityError, match="only be deleted while"):
        conn.execute("DELETE FROM symbol_scan_results WHERE scan_run_id = 'r1' AND symbol = 'TCS'")

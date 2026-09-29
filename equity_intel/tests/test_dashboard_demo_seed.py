"""Tests for scripts/dashboard_demo_seed.py.

db_path_guard.CANONICAL_DB_PATH and DEMO_DB_PATH are monkeypatched to
tmp_path locations for every test, same pattern as
equity_intel/tests/test_connection.py -- this never touches the real
data/equity_intel.db or a real data/equity_intel_demo.db.
"""
import pytest

from equity_intel.persistence import connection, db_path_guard
from scripts.dashboard_demo_seed import FAKE_SYMBOLS, RefusedRealDatabaseError, seed_demo_database


@pytest.fixture
def paths(monkeypatch, tmp_path):
    canonical = tmp_path / "equity_intel.db"
    demo = tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", canonical)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    return canonical, demo


def test_seed_refuses_the_canonical_path(paths):
    canonical, _demo = paths
    with pytest.raises(RefusedRealDatabaseError):
        seed_demo_database(canonical)
    assert not canonical.exists()


def test_seed_refuses_an_arbitrary_path_and_leaves_it_untouched(paths, tmp_path):
    # Allow-list, not deny-list: seed_demo_database must refuse anything
    # that isn't exactly DEMO_DB_PATH, not merely anything that happens to
    # equal CANONICAL_DB_PATH. A pre-existing file at that arbitrary path
    # must survive the refusal completely untouched (no unlink).
    _canonical, _demo = paths
    arbitrary = tmp_path / "some_other_file.db"
    arbitrary.write_text("do not touch me")
    with pytest.raises(RefusedRealDatabaseError):
        seed_demo_database(arbitrary)
    assert arbitrary.exists()
    assert arbitrary.read_text() == "do not touch me"


def test_seed_refuses_a_sibling_path_of_the_demo_database(paths):
    _canonical, demo = paths
    sibling = demo.parent / "equity_intel_demo.db.bak"
    with pytest.raises(RefusedRealDatabaseError):
        seed_demo_database(sibling)
    assert not sibling.exists()


def test_seed_creates_the_demo_database(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    assert demo.exists()


def test_seed_is_rerunnable_and_does_not_accumulate_rows(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    seed_demo_database(demo)

    conn = connection.get_read_only_connection(demo)
    try:
        count = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
    finally:
        conn.close()
    assert count == 4


def test_seed_produces_the_expected_run_lifecycle_mix(paths):
    _canonical, demo = paths
    seed_demo_database(demo)

    conn = connection.get_read_only_connection(demo)
    try:
        statuses = sorted(row[0] for row in conn.execute("SELECT status FROM scan_runs").fetchall())
    finally:
        conn.close()
    assert statuses == ["ABORTED", "COMPLETE", "COMPLETE", "RUNNING"]


def test_seed_covers_all_four_statuses_and_all_four_flags(paths):
    _canonical, demo = paths
    seed_demo_database(demo)

    conn = connection.get_read_only_connection(demo)
    try:
        statuses = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT symbol_data_status FROM symbol_scan_results"
            ).fetchall()
        }
        flags = conn.execute(
            """
            SELECT SUM(history_gaps_flag), SUM(corporate_action_review_flag),
                   SUM(price_break_detected_flag), SUM(non_eq_series_flag)
            FROM symbol_scan_results
            """
        ).fetchone()
    finally:
        conn.close()
    assert statuses == {"VALID", "INSUFFICIENT_HISTORY", "STALE", "FAILED"}
    assert all(count > 0 for count in flags)


def test_seed_gives_failed_and_stale_rows_a_status_reason(paths):
    _canonical, demo = paths
    seed_demo_database(demo)

    conn = connection.get_read_only_connection(demo)
    try:
        rows = conn.execute(
            "SELECT status_reason FROM symbol_scan_results WHERE symbol_data_status IN ('FAILED', 'STALE')"
        ).fetchall()
    finally:
        conn.close()
    assert rows
    assert all(row[0] for row in rows)


def test_seed_aborted_run_has_an_abort_reason(paths):
    _canonical, demo = paths
    seed_demo_database(demo)

    conn = connection.get_read_only_connection(demo)
    try:
        row = conn.execute(
            "SELECT abort_reason FROM scan_runs WHERE status = 'ABORTED'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0]


def test_fake_symbols_has_at_least_thirty_entries():
    assert len(FAKE_SYMBOLS) >= 30


def test_seed_older_complete_run_is_outdated_and_latest_is_not(paths):
    from dashboard import queries

    _canonical, demo = paths
    seed_demo_database(demo)

    conn = connection.get_read_only_connection(demo)
    try:
        rows = {
            row[0]: {"latest_closed_session": row[1]}
            for row in conn.execute(
                "SELECT run_id, latest_closed_session FROM scan_runs WHERE status = 'COMPLETE'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert queries.is_outdated(rows["r-demo-old-complete"]) is True
    assert queries.is_outdated(rows["r-demo-latest-complete"]) is False

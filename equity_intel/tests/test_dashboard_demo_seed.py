"""Tests for scripts/dashboard_demo_seed.py.

db_path_guard.CANONICAL_DB_PATH and DEMO_DB_PATH are monkeypatched to
tmp_path locations for every test, same pattern as
equity_intel/tests/test_connection.py -- this never touches the real
data/equity_intel.db or a real data/equity_intel_demo.db.
"""
from datetime import datetime

import pytest

from equity_intel.persistence import connection, db_path_guard
from scripts.dashboard_demo_seed import (
    BAR_DATES, DEMO_E4_CONFIG, FAKE_SYMBOLS, REVISED_DATE, SESSION_DATE, RefusedRealDatabaseError, _seed_e4_tables,
    seed_demo_database,
)


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
    assert count == 6


def test_seed_produces_the_expected_run_lifecycle_mix(paths):
    _canonical, demo = paths
    seed_demo_database(demo)

    conn = connection.get_read_only_connection(demo)
    try:
        statuses = sorted(row[0] for row in conn.execute("SELECT status FROM scan_runs").fetchall())
    finally:
        conn.close()
    assert statuses == ["ABORTED", "COMPLETE", "COMPLETE", "COMPLETE", "COMPLETE", "RUNNING"]


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


def test_seed_older_complete_run_is_outdated_and_latest_is_current_as_of_its_own_session(paths):
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
    # The demo is deterministic (latest session = Fri 2026-09-25): current that evening,
    # OUTDATED once a later session should have closed.
    assert rows["r-demo-latest-complete"]["latest_closed_session"] == SESSION_DATE
    assert queries.is_outdated(rows["r-demo-latest-complete"], datetime(2026, 9, 25, 19, 0)) is False
    assert queries.is_outdated(rows["r-demo-latest-complete"], datetime(2026, 9, 28, 19, 0)) is True


def _rows(demo, sql):
    conn = connection.get_read_only_connection(demo)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_seed_has_a_newer_smoke_run_after_the_latest_full_run(paths):
    from dashboard import queries

    _canonical, demo = paths
    seed_demo_database(demo)
    conn = connection.get_read_only_connection(demo)
    try:
        assert queries.get_latest_complete_run(conn)["run_id"] == "r-demo-latest-complete"
    finally:
        conn.close()
    smoke = _rows(demo, "SELECT run_id FROM scan_runs WHERE symbols_filter_json IS NOT NULL AND started_at > "
                        "(SELECT started_at FROM scan_runs WHERE run_id='r-demo-latest-complete')")
    assert smoke == [("r-demo-smoke",)]


def test_seed_creates_e4_and_acquired_tables_with_matching_as_of(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    (asof,) = _rows(demo, "SELECT asof_date FROM e4_scan_runs WHERE status='COMPLETE'")[0]
    (session,) = _rows(demo, "SELECT latest_closed_session FROM scan_runs WHERE run_id='r-demo-latest-complete'")[0]
    assert asof == session == SESSION_DATE
    assert _rows(demo, "SELECT COUNT(*) FROM e4_feature_sets")[0][0] > 0
    assert _rows(demo, "SELECT COUNT(*) FROM acquired_observations")[0][0] > 0
    assert _rows(demo, "SELECT COUNT(*) FROM acquired_benchmark")[0][0] > 0
    # FAILED symbols get no E4 rows.
    assert _rows(demo, "SELECT COUNT(*) FROM e4_data_quality_results q JOIN symbol_scan_results r "
                       "ON r.symbol=q.symbol AND r.scan_run_id='r-demo-latest-complete' "
                       "WHERE r.symbol_data_status='FAILED'")[0][0] == 0


def test_seed_snapshots_are_hash_consistent(paths):
    from equity_intel.scanner.snapshots import compute_content_hash_from_stored_row

    _canonical, demo = paths
    seed_demo_database(demo)
    conn = connection.get_read_only_connection(demo)
    try:
        cursor = conn.execute("SELECT * FROM price_fetch_snapshots")
        names = [c[0] for c in cursor.description]
        for row in cursor.fetchall():
            row = dict(zip(names, row))
            assert compute_content_hash_from_stored_row(row) == row["content_hash"]
    finally:
        conn.close()


def test_revisions_between_the_two_newest_full_runs_are_exactly_the_documented_rule(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    pairs = _rows(demo, """
        SELECT a.symbol, a.trading_date, a.close, b.close, a.volume, b.volume, a.content_hash, b.content_hash
        FROM price_fetch_snapshots a JOIN price_fetch_snapshots b
          ON a.symbol = b.symbol AND a.trading_date = b.trading_date
        WHERE a.scan_run_id = 'r-demo-prev-complete' AND b.scan_run_id = 'r-demo-latest-complete'
    """)
    # every bar exists in both runs; a STALE symbol lacks the last date in both, a FAILED symbol has none
    n_stale = sum(1 for sym in FAKE_SYMBOLS if sym[3] == "STALE")
    n_failed = sum(1 for sym in FAKE_SYMBOLS if sym[3] == "FAILED")
    assert n_stale and n_failed
    assert len(pairs) == (len(FAKE_SYMBOLS) - n_failed) * len(BAR_DATES) - n_stale

    # the rule, restated here independently of the seed's implementation
    stale = {sym[0] for sym in FAKE_SYMBOLS if sym[3] == "STALE"}
    expected_close = {(sym[0], "2026-09-24") for i, sym in enumerate(FAKE_SYMBOLS) if i % 6 == 0 and sym[3] != "FAILED"}
    expected_volume = {(sym[0], "2026-09-24") for i, sym in enumerate(FAKE_SYMBOLS) if i % 9 == 0 and sym[3] != "FAILED"}
    differing = {(s, d) for s, d, _c0, _c1, _v0, _v1, h0, h1 in pairs if h0 != h1}
    assert differing == expected_close | expected_volume
    assert {(s, d) for s, d, c0, c1, *_ in pairs if c0 != c1} == expected_close
    assert {(s, d) for s, d, _c0, _c1, v0, v1, *_ in pairs if v0 != v1} == expected_volume
    assert sum(1 for *_x, h0, h1 in pairs if h0 == h1) == len(pairs) - len(differing)

    # hard-coded literals (symbol order is FAKE_SYMBOLS' own): these must hold regardless of how
    # the rule is implemented. Index 0 DEMOAAA (both rules), 6 DEMOPAA (close only: 6%6==0, 6%9!=0),
    # 9 DEMOAUA (volume only: 9%9==0, 9%6!=0), 5 DEMOBAC (neither).
    by_key = {(s, d): (float(c0), float(c1), v0, v1) for s, d, c0, c1, v0, v1, *_ in pairs}  # prices are TEXT
    c0, c1, v0, v1 = by_key[("DEMOAAA", "2026-09-24")]
    assert (c1 - c0, v1 - v0) == (0.75, 12345)
    c0, c1, v0, v1 = by_key[("DEMOPAA", "2026-09-24")]
    assert (c1 - c0, v1 - v0) == (0.75, 0)
    c0, c1, v0, v1 = by_key[("DEMOAUA", "2026-09-24")]
    assert (c1 - c0, v1 - v0) == (0, 12345)
    for key in (("DEMOBAC", "2026-09-24"), ("DEMOAAA", "2026-09-23"), ("DEMOAAA", "2026-09-25")):
        c0, c1, v0, v1 = by_key[key]
        assert (c1, v1) == (c0, v0), key
    assert "DEMOPAB" in stale and ("DEMOPAB", "2026-09-25") not in by_key  # STALE symbol: no bar on the session date


def test_seeded_dates_are_weekdays_only(paths):
    from datetime import date

    _canonical, demo = paths
    seed_demo_database(demo)
    assert all(date.fromisoformat(d).weekday() < 5 for d in BAR_DATES)
    assert date.fromisoformat(REVISED_DATE) in {date.fromisoformat(d) for d in BAR_DATES}
    snapshot_dates = {r[0] for r in _rows(demo, "SELECT DISTINCT trading_date FROM price_fetch_snapshots "
                                                 "WHERE scan_run_id IN ('r-demo-prev-complete','r-demo-latest-complete')")}
    assert snapshot_dates == set(BAR_DATES)
    for (session,) in _rows(demo, "SELECT latest_closed_session FROM scan_runs WHERE latest_closed_session IS NOT NULL"):
        assert date.fromisoformat(session).weekday() < 5, session
    assert all(date.fromisoformat(d).weekday() < 5 for (d,) in _rows(demo, "SELECT DISTINCT trading_date FROM acquired_benchmark"))


def test_seeded_e4_bar_counts_are_consistent_with_the_demo_minimum_history(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    minimum = DEMO_E4_CONFIG["minimum_history_bars"]
    assert minimum == 252
    rows = _rows(demo, """
        SELECT q.symbol, q.status, q.n_bars, q.w52_complete,
               (SELECT COUNT(*) FROM acquired_observations o JOIN e4_scan_runs s ON s.acquisition_run_id = o.run_id WHERE s.scan_id = q.scan_id AND o.symbol = q.symbol)
        FROM e4_data_quality_results q""")
    assert rows
    for symbol, status, n_bars, w52, observed in rows:
        assert observed == n_bars, symbol  # the stored bar count matches the stored bars
        if status == "VALID":
            assert n_bars >= minimum and w52 == 1, symbol
        if status == "INSUFFICIENT_HISTORY":
            assert n_bars < minimum and w52 == 0, symbol
    assert {r[1] for r in rows} >= {"VALID", "INSUFFICIENT_HISTORY"}


def test_seed_e4_tables_refuses_the_canonical_path(paths):
    # connection.connect() would accept the canonical DB (it is on the allow-list), so the
    # seed's own exact-demo-path guard is the only thing standing in the way.
    canonical, _demo = paths
    with pytest.raises(RefusedRealDatabaseError):
        _seed_e4_tables(canonical, "2026-09-25")
    assert not canonical.exists()  # not created


def test_seed_e4_tables_leaves_an_existing_canonical_file_unmodified(paths):
    canonical, _demo = paths
    canonical.write_bytes(b"real data, do not touch")
    before = (canonical.read_bytes(), canonical.stat().st_mtime_ns)
    with pytest.raises(RefusedRealDatabaseError):
        _seed_e4_tables(canonical, "2026-09-25")
    assert (canonical.read_bytes(), canonical.stat().st_mtime_ns) == before


def test_seed_e4_tables_refuses_a_sibling_of_the_demo_path(paths):
    canonical, demo = paths
    sibling = demo.parent / "equity_intel_demo.db.bak"
    with pytest.raises(RefusedRealDatabaseError):
        _seed_e4_tables(sibling, "2026-09-25")
    assert not sibling.exists() and not canonical.exists()


def test_stale_demo_symbols_have_newest_bar_older_than_the_run_session(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    stale = [r[0] for r in _rows(demo, "SELECT symbol FROM symbol_scan_results WHERE scan_run_id='r-demo-latest-complete' "
                                       "AND symbol_data_status='STALE'")]
    assert "DEMOPAB" in stale and len(stale) >= 2
    for scan_run in ("r-demo-latest-complete", "r-demo-prev-complete"):
        for symbol in stale:
            (newest,) = _rows(demo, f"SELECT MAX(trading_date) FROM price_fetch_snapshots WHERE scan_run_id='{scan_run}' "
                                    f"AND symbol='{symbol}'")[0]
            assert newest < SESSION_DATE, (scan_run, symbol)
    # a VALID symbol's newest bar is the session date, and a STALE symbol's E4 observations are older too
    assert _rows(demo, "SELECT MAX(trading_date) FROM price_fetch_snapshots WHERE scan_run_id='r-demo-latest-complete' "
                       "AND symbol='DEMOAAA'")[0][0] == SESSION_DATE
    assert _rows(demo, "SELECT MAX(trading_date) FROM acquired_observations WHERE symbol='DEMOPAB'")[0][0] < SESSION_DATE
    assert _rows(demo, "SELECT MAX(trading_date) FROM acquired_observations WHERE symbol='DEMOAAA'")[0][0] == SESSION_DATE


# ---- run-level counts: derived from the generated rows, never from the seed's own helpers ----

FLAG_COLUMNS = {"history_gaps": "history_gaps_flag", "corporate_action_review": "corporate_action_review_flag",
                "price_break_detected": "price_break_detected_flag", "non_eq_series": "non_eq_series_flag"}


def _run_facts(demo):
    """Per run: stored columns plus counts recounted straight from symbol_scan_results (plain SQL)."""
    import json
    conn = connection.get_read_only_connection(demo)
    try:
        runs = conn.execute(
            "SELECT run_id, status, symbols_filter_json, requested_symbols, successful_symbols, failed_symbols, "
            "status_counts_json, flag_counts_json FROM scan_runs ORDER BY started_at").fetchall()
        facts = {}
        for run_id, status, filt, requested, successful, failed, status_json, flag_json in runs:
            rows = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(symbol_data_status != 'FAILED'), 0), "
                "COALESCE(SUM(symbol_data_status = 'FAILED'), 0) FROM symbol_scan_results WHERE scan_run_id = ?",
                (run_id,)).fetchone()
            by_status = dict(conn.execute(
                "SELECT symbol_data_status, COUNT(*) FROM symbol_scan_results WHERE scan_run_id = ? GROUP BY 1",
                (run_id,)).fetchall())
            by_flag = {name: conn.execute(
                f"SELECT COALESCE(SUM({column}), 0) FROM symbol_scan_results WHERE scan_run_id = ?", (run_id,)).fetchone()[0]
                for name, column in FLAG_COLUMNS.items()}
            facts[run_id] = {
                "status": status, "smoke": filt is not None, "requested": requested, "successful": successful,
                "failed": failed, "rows": rows[0], "non_failed": rows[1], "failed_rows": rows[2],
                "by_status": by_status, "by_flag": by_flag,
                "stored_status": json.loads(status_json) if status_json else None,
                "stored_flags": json.loads(flag_json) if flag_json else None}
        return facts
    finally:
        conn.close()


def test_every_complete_run_records_successful_as_the_non_failed_row_count(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    facts = _run_facts(demo)
    complete = {run_id: f for run_id, f in facts.items() if f["status"] == "COMPLETE"}
    assert {"r-demo-old-complete", "r-demo-prev-complete", "r-demo-latest-complete", "r-demo-smoke"} <= set(complete)
    for run_id, f in complete.items():
        assert f["rows"] > 0, run_id
        assert f["successful"] == f["non_failed"], (run_id, "successful must count every non-FAILED row")
        assert f["failed"] == f["failed_rows"], run_id
        assert f["requested"] == f["rows"], run_id
        assert f["successful"] + f["failed"] == f["requested"], run_id
    full = [f for f in complete.values() if not f["smoke"]]
    assert all(f["failed_rows"] > 0 and f["successful"] < f["requested"] for f in full)  # the realistic case


def test_stored_status_and_flag_counts_still_equal_the_recount_for_every_complete_run(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    for run_id, f in _run_facts(demo).items():
        if f["status"] != "COMPLETE":
            continue
        recount = {s: f["by_status"].get(s, 0) for s in ("VALID", "INSUFFICIENT_HISTORY", "STALE", "FAILED")}
        assert f["stored_status"] == recount, run_id
        assert {k.lower(): v for k, v in f["stored_flags"].items()} == f["by_flag"], run_id


def test_running_and_aborted_demo_runs_have_no_counts_and_no_rows(paths):
    _canonical, demo = paths
    seed_demo_database(demo)
    facts = _run_facts(demo)
    for run_id, expected in (("r-demo-running", "RUNNING"), ("r-demo-aborted", "ABORTED")):
        f = facts[run_id]
        assert f["status"] == expected and f["rows"] == 0, run_id
        assert (f["requested"], f["successful"], f["failed"]) == (None, None, None), run_id  # nothing recorded, not 0


def test_seeding_writes_nothing_under_the_real_data_directory(paths):
    from pathlib import Path
    real_data = Path(__file__).resolve().parents[2] / "data"

    def snapshot():
        return sorted((str(p.relative_to(real_data)), p.stat().st_size, p.stat().st_mtime_ns)
                      for p in real_data.rglob("*") if p.is_file()) if real_data.exists() else []

    before = snapshot()
    _canonical, demo = paths
    seed_demo_database(demo)
    seed_demo_database(demo)
    assert demo.parent != real_data and real_data not in demo.parents  # the guard paths point at tmp_path
    assert snapshot() == before

"""The demo database shows the "E4 older" case: the newest COMPLETE E4 scan is as of the session before the
ScanRun latest closed session.

Every expected value below is written by hand from the calendar and from the demo's design, not read back from the
seed code: 2026-09-25 is a Friday, so the session before it is Thursday 2026-09-24 (one calendar day, one weekday),
and the Thursday before that is 2026-09-23. The demo has 30 symbols, 3 of them FAILED (no E4 rows), 20 VALID,
3 INSUFFICIENT_HISTORY and 4 STALE; 20 feature rows.
"""
import html
from datetime import datetime

import pytest

from dashboard.app import create_app
from equity_intel.persistence import connection, db_path_guard

API, PAGE = "/api/equity/health", "/equity"
FRIDAY_EVENING = datetime(2026, 9, 25, 19, 0, 0)           # after the 18:00 IST cutoff: the expected session is Friday 2026-09-25
MONDAY_EVENING = datetime(2026, 9, 28, 19, 0, 0)           # the expected session is Monday 2026-09-28
SENTENCE = ("The E4 as-of date 2026-09-24 is 1 calendar day(s) (1 weekday(s); weekdays ignore market holidays) older than the "
            "ScanRun's latest closed session 2026-09-25. The two sets of counts describe different sessions.")
STATUS_MIX = {"VALID": 20, "INSUFFICIENT_HISTORY": 3, "STALE": 4}


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    from scripts import dashboard_demo_seed as seed
    path = tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", tmp_path / "equity_intel.db")
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", path)
    seed.seed_demo_database(path)
    return path


def _sql(path, sql, params=()):
    conn = connection.get_read_only_connection(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _app(clock):
    app = create_app(demo=True)
    app.config["HEALTH_CLOCK"] = lambda: clock
    return app


def _body(clock):
    return _app(clock).test_client().get(API).get_json()


def _rows(body):
    return {r["id"]: r for r in body["freshness"]}


# ---------------------------------------------------------------- the seeded rows

def test_there_are_two_complete_e4_scans_and_the_newer_started_one_is_as_of_the_earlier_session(demo):
    scans = _sql(demo, "SELECT scan_id, asof_date, status FROM e4_scan_runs ORDER BY started_at")
    assert scans == [("demo-e4-1", "2026-09-25", "COMPLETE"), ("demo-e4-2", "2026-09-24", "COMPLETE")]
    assert _sql(demo, "SELECT asof_date FROM e4_scan_runs WHERE status = 'COMPLETE' ORDER BY started_at DESC LIMIT 1") == [("2026-09-24",)]
    assert _sql(demo, "SELECT latest_closed_session FROM scan_runs WHERE run_id = 'r-demo-latest-complete'") == [("2026-09-25",)]


@pytest.mark.parametrize("scan_id", ["demo-e4-1", "demo-e4-2"])
def test_each_e4_scan_has_the_same_status_mix_and_consistent_rows(demo, scan_id):
    counts = dict(_sql(demo, "SELECT status, COUNT(*) FROM e4_data_quality_results WHERE scan_id = ? GROUP BY status", (scan_id,)))
    assert counts == STATUS_MIX and sum(counts.values()) == 27                       # 30 symbols minus 3 FAILED
    (features,) = _sql(demo, "SELECT COUNT(*) FROM e4_feature_sets WHERE scan_id = ?", (scan_id,))[0]
    assert features == 20 == counts["VALID"]
    # a feature row exists for exactly the VALID symbols
    assert _sql(demo, "SELECT COUNT(*) FROM e4_feature_sets f JOIN e4_data_quality_results q ON q.scan_id = f.scan_id AND q.symbol = f.symbol "
                      "WHERE f.scan_id = ? AND q.status = 'VALID'", (scan_id,)) == [(20,)]
    # a quality row's stored bar count equals the bars stored for that symbol in that scan's own acquisition run
    assert _sql(demo, "SELECT COUNT(*) FROM e4_data_quality_results q JOIN e4_scan_runs s ON s.scan_id = q.scan_id "
                      "WHERE q.scan_id = ? AND q.n_bars != (SELECT COUNT(*) FROM acquired_observations o "
                      "WHERE o.run_id = s.acquisition_run_id AND o.symbol = q.symbol)", (scan_id,)) == [(0,)]
    # the 3 FAILED ScanRun symbols have no E4 quality row
    assert _sql(demo, "SELECT COUNT(*) FROM e4_data_quality_results q JOIN symbol_scan_results r ON r.symbol = q.symbol "
                      "AND r.scan_run_id = 'r-demo-latest-complete' WHERE q.scan_id = ? AND r.symbol_data_status = 'FAILED'", (scan_id,)) == [(0,)]


@pytest.mark.parametrize("scan_id, acquisition, asof, stale_last", [("demo-e4-1", "demo-acq-1", "2026-09-25", "2026-09-24"),
                                                                    ("demo-e4-2", "demo-acq-2", "2026-09-24", "2026-09-23")])
def test_the_bars_of_each_scan_end_on_its_own_as_of_date(demo, scan_id, acquisition, asof, stale_last):
    assert _sql(demo, "SELECT acquisition_run_id FROM e4_scan_runs WHERE scan_id = ?", (scan_id,)) == [(acquisition,)]
    assert _sql(demo, "SELECT MAX(trading_date) FROM acquired_benchmark WHERE run_id = ?", (acquisition,)) == [(asof,)]
    assert _sql(demo, "SELECT DISTINCT last_date FROM e4_feature_sets WHERE scan_id = ?", (scan_id,)) == [(asof,)]
    ends = {status: {d for (d,) in _sql(demo, "SELECT MAX(o.trading_date) FROM e4_data_quality_results q JOIN acquired_observations o "
                                              "ON o.run_id = ? AND o.symbol = q.symbol WHERE q.scan_id = ? AND q.status = ? GROUP BY q.symbol",
                                        (acquisition, scan_id, status))}
            for status in STATUS_MIX}
    assert ends == {"VALID": {asof}, "INSUFFICIENT_HISTORY": {asof}, "STALE": {stale_last}}
    # no weekend date among the stored bars of this acquisition run (Mon-Fri only)
    assert _sql(demo, "SELECT COUNT(*) FROM acquired_observations WHERE run_id = ? AND strftime('%w', trading_date) IN ('0', '6')", (acquisition,)) == [(0,)]


def test_the_scanrun_side_of_the_demo_is_unchanged(demo):
    assert sorted(_sql(demo, "SELECT symbol_data_status, COUNT(*) FROM symbol_scan_results WHERE scan_run_id = 'r-demo-latest-complete' "
                             "GROUP BY symbol_data_status")) == [("FAILED", 3), ("INSUFFICIENT_HISTORY", 3), ("STALE", 4), ("VALID", 20)]
    assert _sql(demo, "SELECT COUNT(*) FROM scan_runs") == [(6,)]
    assert {r[0] for r in _sql(demo, "SELECT scan_id FROM e4_scan_runs")} == {"demo-e4-1", "demo-e4-2"}


# ---------------------------------------------------------------- what the panel says on the Friday evening of the ScanRun session

def test_the_relationship_says_the_e4_date_is_one_session_older(demo):
    body = _body(FRIDAY_EVENING)
    rel = body["relationship"]
    assert (rel["state"], rel["scanrun_date"], rel["e4_date"], rel["calendar_days"], rel["weekdays"]) == ("e4_older", "2026-09-25", "2026-09-24", 1, 1)
    assert rel["sentence"] == SENTENCE
    assert body["layers"]["scanrun"]["latest_closed_session"] == "2026-09-25" and body["layers"]["e4"]["asof_date"] == "2026-09-24"
    assert body["layers"]["e4"]["scan_id"] == "demo-e4-2"


def test_f1_is_ok_f2_and_f3_warn(demo):
    rows = _rows(_body(FRIDAY_EVENING))
    assert rows["F1"]["state"] == "OK"
    assert rows["F2"]["state"] == "WARN" and rows["F2"]["weekdays_behind"] == 1 and rows["F2"]["expected_session"] == "2026-09-25"
    assert rows["F3"]["state"] == "WARN" and rows["F3"]["detail"] == [SENTENCE]


def test_only_the_e4_banner_appears_and_it_states_its_basis(demo):
    banners = _body(FRIDAY_EVENING)["banners"]
    assert [(b["layer"], b["kind"], b["stored"], b["expected"]) for b in banners] == [("E4", "OUTDATED", "2026-09-24", "2026-09-25")]
    assert banners[0]["compared"] == "the E4 as-of date"
    assert "Compared: the E4 as-of date 2026-09-24 with the expected latest session 2026-09-25" in banners[0]["text"]
    assert "Market holidays are unknown" in banners[0]["text"]


def test_the_counts_are_the_same_in_both_layers_but_nothing_is_added_across_them(demo):
    layers = _body(FRIDAY_EVENING)["layers"]
    assert layers["e4"]["status_counts"] == STATUS_MIX and layers["e4"]["denominator"] == 27 and layers["e4"]["feature_sets"] == 20
    assert layers["scanrun"]["denominator"] == 30 and layers["scanrun"]["status_recount"] == {**STATUS_MIX, "FAILED": 3}


def test_the_equity_page_shows_the_sentence_f2_f3_and_only_the_e4_banner(demo):
    page = html.unescape(_app(FRIDAY_EVENING).test_client().get(PAGE).get_data(as_text=True))
    assert SENTENCE in page
    assert 'data-layer="E4" data-kind="OUTDATED"' in page and 'data-layer="ScanRun"' not in page
    assert "demo-e4-2" in page and "r-demo-latest-complete" in page


def test_on_the_monday_evening_both_layers_are_behind_by_their_own_amounts(demo):
    # expected session Monday 2026-09-28: the Fri 09-25 ScanRun session is 1 weekday behind, the Thu 09-24 E4 date is 2
    body = _body(MONDAY_EVENING)
    rows = _rows(body)
    assert (rows["F1"]["state"], rows["F1"]["weekdays_behind"], rows["F2"]["state"], rows["F2"]["weekdays_behind"]) == ("WARN", 1, "WARN", 2)
    assert [b["layer"] for b in body["banners"]] == ["ScanRun", "E4"]
    assert body["relationship"]["sentence"] == SENTENCE                                    # the relationship does not depend on the clock

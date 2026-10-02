"""E4 indicator columns on the read-only dashboard (dashboard/queries.py, dashboard/app.py)."""
import json

import pytest

from dashboard.app import create_app
from equity_intel.persistence import connection
from equity_intel.tests.test_dashboard import _build_fixture_db, db_path  # noqa: F401  (fixture reuse)

_CONFIG = {"ema_short": 20, "ema_medium": 50, "ema_long": 200, "rsi_period": 14, "roc_lookback": 10,
           "relative_return_lookback": 60, "rvol_window": 20, "high_window": 252, "atr_period": 14}


def _add_e4_scan(path, *, scan_id="e4-1", status="COMPLETE", started="2026-09-27T10:00:00", asof="2026-09-25"):
    conn = connection.connect(path)  # creates the e4_* tables next to the scanner tables
    try:
        conn.execute(
            "INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,status,asof_date,calendar_status,indicator_config_json) "
            "VALUES(?,?,?,?,?,?,?)", (scan_id, "acq-1", started, status, asof, "PROVISIONAL", json.dumps(_CONFIG)))
        conn.execute(
            "INSERT INTO e4_feature_sets(scan_id,symbol,last_date,ema_short,ema_medium,ema_long,rsi,roc,relative_return,"
            "relative_volume,distance_from_high,prior_high_long,atr_percent) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (scan_id, "AAA", asof, 101.5, 100.25, 98.0, 55.5, 1.25, None, 1.1, 4.5, 110.0, 2.0))
        conn.execute("INSERT INTO e4_data_quality_results(scan_id,symbol,status,n_bars,break_date,break_ratio) VALUES(?,?,?,?,?,?)",
                     (scan_id, "AAA", "VALID", 252, "2026-03-01", 0.35))
        conn.commit()
    finally:
        conn.close()


def _candidates(path):
    return create_app(demo=False, db_path=path).test_client().get("/api/equity/candidates").get_json()


def test_candidates_without_e4_tables_are_unchanged(db_path):
    _build_fixture_db(db_path)
    data = _candidates(db_path)
    assert data["e4_scan"] is None
    assert all("e4" not in row for row in data["results"])
    assert data["scoring_status"] == "BLOCKED_B2"


def test_candidates_carry_e4_features_and_never_default_missing_to_zero(db_path):
    _build_fixture_db(db_path)
    _add_e4_scan(db_path)
    data = _candidates(db_path)
    rows = {r["symbol"]: r for r in data["results"]}
    assert rows["AAA"]["e4"]["rsi"] == 55.5 and rows["AAA"]["e4"]["ema_long"] == 98.0
    assert rows["AAA"]["e4"]["relative_return"] is None  # missing stays None, not 0
    assert rows["AAA"]["e4"]["break_date"] == "2026-03-01"
    assert rows["BBB"]["e4"] is None and rows["CCC"]["e4"] is None  # no feature row -> no values invented
    assert data["e4_scan"]["scan_id"] == "e4-1" and data["e4_scan"]["config"]["ema_medium"] == 50
    assert data["scoring_status"] == "BLOCKED_B2" and "rank" not in json.dumps(data).lower().replace("unranked", "")


def test_e4_as_of_mismatch_with_the_scan_run_is_reported(db_path):
    _build_fixture_db(db_path, latest_closed_session="2026-09-25")
    _add_e4_scan(db_path, asof="2026-09-24")
    e4 = _candidates(db_path)["e4_scan"]
    assert e4["as_of_matches_run"] is False and e4["run_latest_closed_session"] == "2026-09-25"


def test_e4_as_of_match_is_reported(db_path):
    _build_fixture_db(db_path, latest_closed_session="2026-09-25")
    _add_e4_scan(db_path, asof="2026-09-25")
    assert _candidates(db_path)["e4_scan"]["as_of_matches_run"] is True


def test_only_a_complete_e4_scan_is_used(db_path):
    _build_fixture_db(db_path)
    _add_e4_scan(db_path, scan_id="good", started="2026-09-26T10:00:00")
    _add_e4_scan(db_path, scan_id="newer-failed", status="FAILED", started="2026-09-27T10:00:00")
    assert _candidates(db_path)["e4_scan"]["scan_id"] == "good"


def test_stock_endpoint_includes_e4_features(db_path):
    _build_fixture_db(db_path)
    _add_e4_scan(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/stock/AAA").get_json()
    assert data["e4_features"]["roc"] == 1.25 and data["e4_scan"]["scan_id"] == "e4-1"
    assert client.get("/api/equity/stock/BBB").get_json()["e4_features"] is None


def test_page_renders_with_e4_support(db_path):
    _build_fixture_db(db_path)
    response = create_app(demo=False, db_path=db_path).test_client().get("/equity")
    assert response.status_code == 200 and b"E4 indicators" in response.data

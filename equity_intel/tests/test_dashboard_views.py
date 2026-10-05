"""Descriptive dashboard views: breadth, sector strength, data quality, scanner
filters/sorting, stock chart and provenance. All read-only; none may rank,
score or band."""
import json

import pytest

from dashboard.app import create_app
from equity_intel.persistence import connection
from equity_intel.tests.test_dashboard import _build_fixture_db, db_path  # noqa: F401  (fixture reuse)

_CONFIG = {"ema_short": 20, "ema_medium": 50, "ema_long": 200, "rsi_period": 14, "roc_lookback": 10,
           "relative_return_lookback": 60, "rvol_window": 20, "high_window": 252, "atr_period": 14}

# symbol: (ema_s, ema_m, ema_l, rsi, roc, rel, rvol, dist, close)
_FEATURES = {
    "AAA": (101.0, 99.0, 90.0, 62.0, 2.0, 1.5, 1.8, 0.0, 100.0),    # above medium+long EMA, below short; at its high
    "BBB": (105.0, 104.0, None, 35.0, -3.0, None, None, 12.0, 100.0),  # below short+medium, no long EMA
    "CCC": (99.0, 98.0, 97.0, 48.0, 0.5, -2.0, 0.9, 6.0, 100.0),    # above all three EMAs
}


@pytest.fixture
def populated(db_path):
    _build_fixture_db(db_path)
    conn = connection.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,status,asof_date,calendar_status,indicator_config_json) "
            "VALUES('e4-1','acq-1','2026-09-27T10:00:00','COMPLETE','2026-09-25','PROVISIONAL',?)", (json.dumps(_CONFIG),))
        for sym, (es, em, el_, rsi, roc, rel, rvol, dist, close) in _FEATURES.items():
            conn.execute(
                "INSERT INTO e4_feature_sets(scan_id,symbol,last_date,ema_short,ema_medium,ema_long,rsi,roc,relative_return,"
                "relative_volume,distance_from_high,prior_high_long,atr_percent) VALUES('e4-1',?,?,?,?,?,?,?,?,?,?,?,?)",
                (sym, "2026-09-25", es, em, el_, rsi, roc, rel, rvol, dist, 110.0, 2.0))
            conn.execute(
                "INSERT INTO acquired_observations(run_id,symbol,trading_date,open,high,low,close,volume,source_vendor,"
                "source_endpoint,retrieval_timestamp,instrument_key,exchange,calendar_status,adjustment_status,data_version) "
                "VALUES('acq-1',?,?,?,?,?,?,?,'v','e','t','k','NSE','P','A','1')",
                (sym, "2026-09-25", close, close, close, close, 1000))
        conn.execute("INSERT INTO e4_data_quality_results(scan_id,symbol,status,reason,n_bars,w52_complete,break_date,break_ratio,volume_usable) "
                     "VALUES('e4-1','AAA','VALID',NULL,252,1,NULL,NULL,1)")
        conn.execute("INSERT INTO e4_data_quality_results(scan_id,symbol,status,reason,n_bars,w52_complete,break_date,break_ratio,volume_usable) "
                     "VALUES('e4-1','BBB','INSUFFICIENT_HISTORY','40 bars; 252 required',40,0,'2026-03-01',0.4,0)")
        conn.commit()
    finally:
        conn.close()
    return create_app(demo=False, db_path=db_path).test_client()


def test_summary_has_breadth_with_denominators_and_safety_panel(populated):
    data = populated.get("/api/equity/summary").get_json()
    above = data["breadth"]["above_ema"]
    assert above["short"]["count"] == 1 and above["short"]["of"] == 3   # only CCC closes above its short EMA
    assert above["medium"]["count"] == 2 and above["medium"]["of"] == 3
    assert above["long"]["of"] == 2          # BBB has no long EMA: out of the denominator, visibly
    assert data["breadth"]["high_proximity"]["at_high"] == 1
    assert data["breadth"]["high_proximity"]["buckets"][-3]["count"] == 1   # 6% is in the 5-10 bucket
    assert data["safety"]["broker_execution"] == "DISABLED" and data["safety"]["scoring"] == "BLOCKED_B2"


def test_summary_without_e4_has_null_breadth_but_still_has_data_quality(db_path):
    _build_fixture_db(db_path)
    data = create_app(demo=False, db_path=db_path).test_client().get("/api/equity/summary").get_json()
    assert data["breadth"] is None and data["e4_scan"] is None
    assert data["data_quality"]["symbols_with_warnings"] >= 1


def test_data_quality_gives_a_reason_for_every_warning_and_drops_nothing(populated):
    dq = populated.get("/api/equity/summary").get_json()["data_quality"]
    assert dq["symbols_total"] == 3
    by_symbol = {i["symbol"]: i for i in dq["issues"]}
    assert set(by_symbol) == {"BBB", "CCC"}         # AAA is clean
    assert dq["symbols_without_warning"] == 1
    for issue in dq["issues"]:
        assert issue["warnings"] and all(w["message"] for w in issue["warnings"])
    codes = {w["code"] for w in by_symbol["BBB"]["warnings"]}
    assert {"FAILED", "history_gaps", "corporate_action_review", "e4_INSUFFICIENT_HISTORY",
            "e4_no_full_high_window", "e4_volume_unusable", "e4_break"} <= codes


def test_sector_strength_is_alphabetical_and_descriptive(populated):
    data = populated.get("/api/equity/sectors").get_json()
    names = [s["sector"] for s in data["strength"]]
    assert names == sorted(names)
    it = next(s for s in data["strength"] if s["sector"] == "IT")
    assert it["n"] == 2 and it["above_ema_medium"] == {"count": 1, "of": 2, "pct": 50.0}
    assert "rank" not in json.dumps(data).lower().replace("unranked", "")


def test_scanner_range_filters_sector_and_sorting(populated):
    def symbols(query):
        res = populated.get("/api/equity/candidates?" + query)
        assert res.status_code == 200, res.get_json()
        return [r["symbol"] for r in res.get_json()["results"]]

    assert symbols("rsi_min=40") == ["AAA", "CCC"]
    assert symbols("rsi_max=50") == ["BBB", "CCC"]
    assert symbols("dist_max=7") == ["AAA", "CCC"]
    assert symbols("rvol_min=1") == ["AAA"]            # BBB (no RVOL value) is excluded by the filter, not guessed
    assert symbols("sector=Banking") == ["CCC"]
    assert symbols("sort=rsi&sort_dir=desc") == ["AAA", "CCC", "BBB"]
    assert symbols("sort=relative_return&sort_dir=asc") == ["CCC", "AAA", "BBB"]  # NULL (BBB) always last
    assert symbols("sort=roc&sort_dir=desc&sector=IT") == ["AAA", "BBB"]


def test_scanner_rejects_bad_sort_and_bad_numbers(populated):
    assert populated.get("/api/equity/candidates?sort=password").status_code == 400
    assert populated.get("/api/equity/candidates?sort=rsi&sort_dir=sideways").status_code == 400
    assert populated.get("/api/equity/candidates?rsi_min=abc").status_code == 400
    assert populated.get("/api/equity/candidates?rsi_min=nan").status_code == 400
    assert populated.get("/api/equity/candidates?sort=symbol;DROP TABLE x").status_code == 400


def test_e4_filters_without_an_e4_scan_are_a_clear_400_and_base_sort_still_works(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    assert client.get("/api/equity/candidates?rsi_min=40").status_code == 400
    res = client.get("/api/equity/candidates?sort=symbol&sort_dir=desc")
    assert [r["symbol"] for r in res.get_json()["results"]] == ["CCC", "BBB", "AAA"]


def test_stock_endpoint_has_chart_data_quality_and_provenance(populated):
    data = populated.get("/api/equity/stock/BBB").get_json()
    assert data["chart"]["bars"][-1]["trading_date"] == "2026-09-25"
    assert data["chart"]["break_date"] == "2026-03-01"
    assert data["chart"]["ema"]["short"]["period"] == 20
    assert data["data_quality"]["issues"][0]["symbol"] == "BBB"
    prov = data["provenance"]
    assert prov["run_id"] == "r1" and prov["universe_version"] == "u" and prov["calendar_source"] == "test-cal"
    assert prov["e4_quality"]["status"] == "INSUFFICIENT_HISTORY"
    assert data["candles"][0]["content_hash"] == "hash-BBB"


def test_stock_endpoint_without_e4_has_no_chart(db_path):
    _build_fixture_db(db_path)
    data = create_app(demo=False, db_path=db_path).test_client().get("/api/equity/stock/AAA").get_json()
    assert data["chart"] is None and data["provenance"]["run_id"] == "r1"


def test_new_views_add_no_routes_and_no_write_methods(populated):
    app = populated.application
    rules = sorted(r.rule for r in app.url_map.iter_rules() if r.endpoint != "static")
    assert rules == ["/api/equity/candidates", "/api/equity/scan-history", "/api/equity/sectors",
                     "/api/equity/stock/<symbol>", "/api/equity/summary", "/equity"]
    for rule in rules:
        assert populated.post(rule.replace("<symbol>", "AAA")).status_code in (404, 405)


def test_summary_reports_measured_history_depth(populated):
    h = populated.get("/api/equity/summary").get_json()["history"]
    assert h["first_date"] == h["last_date"] == "2026-09-25" and h["sessions"] == 1 and h["symbols"] == 3


def test_e4_feature_objects_carry_close_and_window_high(populated):
    rows = {r["symbol"]: r for r in populated.get("/api/equity/candidates").get_json()["results"]}
    assert rows["AAA"]["e4"]["close"] == 100.0 and rows["AAA"]["e4"]["window_high"] == 110.0
    stock = populated.get("/api/equity/stock/CCC").get_json()
    assert stock["e4_features"]["close"] == 100.0


def test_research_and_gated_tabs_are_static_and_show_no_model_output(populated):
    page = populated.get("/equity").get_data(as_text=True)
    assert "SPECIFICATION / DATA PREPARATION" in page and "GATED" in page and "NOT RUN" in page
    assert "RESEARCH" in page and "Trade Research" in page
    lowered = page.lower()
    for forbidden in ("auc ", "probability", "expected return", "buy", "sell", "log loss", "accuracy"):
        assert forbidden not in lowered, forbidden

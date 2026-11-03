"""PROVISIONAL v0 persistence: eligibility, ranking, idempotence."""
from equity_intel.persistence import connection as persistence_connection
from equity_intel.persistence import db_path_guard
from equity_intel.scoring import persist_v0
from equity_intel.tests.test_dashboard import _build_fixture_db, db_path  # noqa: F401  (fixture reuse)

STRONG = dict(ema_short=105.0, ema_medium=100.0, ema_long=90.0, ema_medium_lag=95.0, rsi=75, roc=12,
              relative_return=7, relative_volume=3.5, distance_from_high=1.0, prior_high_short=108.0,
              prior_high_medium=109.0, prior_high_long=111.0, atr_percent=1.5, close=110.0)


def _seed(c, symbol, status="VALID", break_date=None, n_bars=252, w52=1, **features):
    f = dict(STRONG, **features)
    c.execute("INSERT INTO e4_data_quality_results VALUES(?,?,?,?,?,?,?,?,?)",
              ("s1", symbol, status, None, n_bars, w52, break_date, None, 1))
    c.execute("INSERT INTO e4_feature_sets(scan_id,symbol,last_date,ema_short,ema_medium,ema_long,rsi,roc,relative_return,"
              "relative_volume,distance_from_high,prior_high_long,atr_percent,ema_medium_lag,prior_high_short,prior_high_medium,close) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ("s1", symbol, "2026-10-23", f["ema_short"], f["ema_medium"], f["ema_long"], f["rsi"], f["roc"],
               f["relative_return"], f["relative_volume"], f["distance_from_high"], f["prior_high_long"], f["atr_percent"],
               f["ema_medium_lag"], f["prior_high_short"], f["prior_high_medium"], f["close"]))


def test_score_scan_ranks_candidates_and_excludes_ineligible(tmp_path, monkeypatch):
    database = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    with persistence_connection.connect(database) as c:
        c.execute("INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,completed_at,status,asof_date,calendar_status,"
                  "constituents_sha256,instrument_master_sha256,indicator_config_json) VALUES('s1','a','t','t','COMPLETE','2026-10-23','PROVISIONAL','x','y','{}')")
        _seed(c, "BBB")                                     # 100
        _seed(c, "AAA")                                     # 100, ties break by symbol
        _seed(c, "WEAK", rsi=30, roc=-1, relative_return=-9, relative_volume=0.5, distance_from_high=30.0, close=95.0,
              prior_high_short=108.0, prior_high_medium=109.0)  # low composite, not a candidate
        _seed(c, "BRK", break_date="2025-01-01")            # break flag -> excluded
        _seed(c, "SHORT", status="INSUFFICIENT_HISTORY", ema_long=None)  # status excluded
        _seed(c, "NOVOL", relative_volume=None)             # composite None
        summary = persist_v0.score_scan(c, "s1")
        rows = {r["symbol"]: dict(r) for r in c.execute("SELECT * FROM e4_provisional_scores")}
        assert summary["scored"] == 6 and summary["candidates"] == 2
        assert (rows["AAA"]["rank"], rows["BBB"]["rank"]) == (1, 2) and rows["AAA"]["composite"] == 100
        assert rows["WEAK"]["candidate"] == 0 and rows["WEAK"]["exclusion"] is None and rows["WEAK"]["rank"] is None
        assert rows["BRK"]["exclusion"] == "CORPORATE_ACTION_BREAK_FLAG" and rows["BRK"]["candidate"] == 0
        assert rows["SHORT"]["exclusion"] == "DATA_STATUS_INSUFFICIENT_HISTORY"
        assert rows["NOVOL"]["composite"] is None and rows["NOVOL"]["exclusion"] == "COMPOSITE_NONE"
        assert all(r["label"] == "PROVISIONAL - not B2-authoritative" for r in rows.values())
        horizons = [dict(r) for r in c.execute("SELECT * FROM e4_provisional_horizons")]
        assert len(horizons) == 12  # 6 symbols x 2 horizons
        short = {h["symbol"]: h for h in horizons if h["horizon"] == "short"}
        assert short["AAA"]["rank"] == 1 and short["BBB"]["rank"] == 2 and short["BRK"]["exclusion"] == "CORPORATE_ACTION_BREAK_FLAG"
        assert short["NOVOL"]["exclusion"] == "COMPOSITE_NONE" and short["WEAK"]["candidate"] == 0
        assert summary["horizons"]["short"]["candidates"] == 2 and summary["horizons"]["medium"]["candidates"] == 2
        persist_v0.score_scan(c, "s1")  # idempotent
        assert c.execute("SELECT COUNT(*) FROM e4_provisional_horizons").fetchone()[0] == 12
        assert c.execute("SELECT COUNT(*) FROM e4_provisional_scores").fetchone()[0] == 6


def test_score_scan_refuses_non_complete_scan(tmp_path, monkeypatch):
    import pytest
    database = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    with persistence_connection.connect(database) as c:
        with pytest.raises(RuntimeError, match="not a COMPLETE"):
            persist_v0.score_scan(c, "missing")


def test_signals_view_is_labelled_provisional_and_read_only(db_path):
    from dashboard import signals
    from dashboard.app import create_app
    _build_fixture_db(db_path)
    with persistence_connection.connect(db_path) as c:
        assert signals.build(c)["available"] is False  # table not created yet: honest empty state
        c.execute("INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,completed_at,status,asof_date,calendar_status,"
                  "constituents_sha256,instrument_master_sha256,indicator_config_json) VALUES('s1','a','t','t','COMPLETE','2026-10-23','PROVISIONAL','x','y','{}')")
        _seed(c, "AAA")
        persist_v0.score_scan(c, "s1")
        body = signals.build(c)
        assert body["available"] and body["candidates"][0]["symbol"] == "AAA" and body["candidates"][0]["watchlist"] is True
        assert body["meta"]["label"] == "PROVISIONAL - not B2-authoritative"
    client = create_app(db_path=db_path).test_client()
    api = client.get("/api/equity/signals").get_json()
    assert api["candidates"][0]["symbol"] == "AAA"
    assert api["horizons"]["short"][0]["symbol"] == "AAA" and api["horizons"]["medium"][0]["score"] == 100
    assert client.post("/equity/signals").status_code in (404, 405)

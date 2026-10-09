"""GET /api/equity/health: the JSON route over dashboard/health.build.

Every case builds its own tmp_path database and injects the clock through app.config["HEALTH_CLOCK"]; nothing reads the
real data/ files and nothing depends on the host clock except the one test that checks the default clock.
Reference calendar: Wed 2026-10-07, Thu 10-08, Fri 10-09, Mon 10-12.
"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone

import pytest

from dashboard import health
from dashboard.app import create_app
from equity_intel.config import IST
from equity_intel.persistence import connection, db_path_guard
from equity_intel.persistence.schema import SCHEMA_VERSION
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_freshness_queries import _add_e4_scan
from equity_intel.tests.test_dashboard_health import (
    FILE_INFO, NOW, _complete, _keys, _rows, _two_layer_db_with_reasons)
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run, _ro

API = "/api/equity/health"


def _app(db_path, now=NOW, demo=False):
    app = create_app(demo=demo, db_path=db_path)
    if now is not None:
        app.config["HEALTH_CLOCK"] = lambda: now
    return app


def _populate(db):
    _complete(db, "r1", "2026-10-07T17:00:00", session="2026-10-07", symbols=[("AAA", "VALID", []), ("BBB", "STALE", [])])
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1)


def _body(db, now=NOW):
    res = _app(db, now).test_client().get(API)
    assert res.status_code == 200
    return res.get_json()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- shape, parity and the clock

def test_the_response_has_the_panel_shape(db):
    _populate(db)
    body = _body(db)
    assert set(body) == {"demo", "title", "scoring_status", "now", "now_text", "holiday_caveat", "expected_session", "session_cutoff_hour_ist",
                         "layers", "relationship", "layer_disagreements", "banners", "freshness"}
    assert body["demo"] is False and body["title"] == health.TITLE and body["scoring_status"] == "BLOCKED_B2"
    assert [r["id"] for r in body["freshness"]] == ["F1", "F2", "F3", "F4a", "F4b", "F5", "F6", "F7", "F8a", "F8b", "F9"]
    assert set(body["layers"]) == {"scanrun", "e4"} and body["layers"]["scanrun"]["run_id"] == "r1" and body["layers"]["e4"]["scan_id"] == "e4-1"
    assert body["now"] == NOW.isoformat() and body["now_text"] == "now (IST) 2026-10-08 09:30:00"


def test_the_body_is_the_builders_output_for_the_same_clock(db):
    _populate(db)
    conn = _ro(db)
    try:
        expected = health.build(conn, NOW, health.read_db_file_info(db))
    finally:
        conn.close()
    got = _body(db)
    assert got.pop("demo") is False
    assert got == json.loads(json.dumps(expected))


def test_the_injected_clock_decides_the_states(db):
    _populate(db)
    assert _rows(_body(db, datetime(2026, 10, 8, 9, 30, 0)))["F1"]["state"] == "OK"        # expected session Wed 10-07
    behind = _rows(_body(db, datetime(2026, 10, 12, 10, 0, 0)))["F1"]
    assert behind["state"] == "WARN" and "weekday(s) behind" in behind["value"] + " ".join(behind["detail"])
    assert _body(db, datetime(2026, 10, 12, 10, 0, 0))["now"] == "2026-10-12T10:00:00"


def test_an_aware_clock_is_read_as_ist(db):
    _populate(db)
    aware = datetime(2026, 10, 8, 9, 30, 0, tzinfo=IST)
    assert _body(db, aware)["now"] == "2026-10-08T09:30:00"
    assert _body(db, datetime(2026, 10, 8, 4, 0, 0, tzinfo=timezone.utc))["now"] == "2026-10-08T09:30:00"       # 04:00 UTC is 09:30 IST


def test_the_default_clock_is_the_current_ist_time(db):
    _populate(db)
    res = create_app(demo=False, db_path=db).test_client().get(API)
    now = datetime.fromisoformat(res.get_json()["now"])
    assert abs((datetime.now(IST).replace(tzinfo=None) - now).total_seconds()) < 120


def test_real_shape_friday_scan_before_the_cutoff_is_one_weekday_behind_after_the_cutoff_only(db):
    # a real scan finishing before 18:00 IST on Friday 2026-10-09 has Thursday as its latest closed session
    _complete(db, "r-fri", "2026-10-09T17:00:00", session="2026-10-08", symbols=[("AAA", "VALID", [])])
    after = _rows(_body(db, datetime(2026, 10, 9, 18, 2, 0, tzinfo=IST)))["F1"]
    assert after["state"] == "WARN" and "1 weekday(s) behind" in " ".join([after["value"], *after["detail"]])
    assert health.HOLIDAY_CAVEAT in " ".join([after["value"], *after["detail"]]) and "market holidays" in " ".join(after["detail"])
    assert "2026-10-09" in after["value"] + " ".join(after["detail"])                      # the expected session is that Friday
    before = _rows(_body(db, datetime(2026, 10, 9, 17, 58, 0, tzinfo=IST)))["F1"]
    assert before["state"] == "OK" and "weekday(s) behind" not in " ".join([before["value"], *before["detail"]])


# ---------------------------------------------------------------- missing database, version mismatch, other methods

@pytest.fixture
def db_path(monkeypatch, tmp_path):
    """The canonical path in tmp_path, not created."""
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    return path


def test_a_missing_database_gives_the_same_body_and_status_as_the_other_routes(db_path):
    client = create_app(demo=False, db_path=db_path).test_client()
    other = client.get("/api/equity/summary")
    res = client.get(API)
    assert (res.status_code, res.get_json()) == (other.status_code, other.get_json()) == (200, {
        "demo": False, "status": "no_scans_yet", "message": "No scans have been recorded yet."})


def test_a_version_mismatch_gives_the_same_body_and_status_as_the_other_routes(db_path):
    conn = connection.get_connection(db_path)
    try:
        connection.initialize_schema(conn)
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))
        conn.commit()
    finally:
        conn.close()
    client = create_app(demo=False, db_path=db_path).test_client()
    other = client.get("/api/equity/summary")
    res = client.get(API)
    assert (res.status_code, res.get_json()) == (other.status_code, other.get_json())
    assert res.status_code == 200 and res.get_json()["status"] == "version_mismatch" and str(SCHEMA_VERSION + 1) in res.get_json()["message"]


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_only_get_is_allowed(db, method):
    _populate(db)
    before = _sha(db)
    res = getattr(_app(db).test_client(), method)(API)
    assert res.status_code == 405 and "GET" in res.headers["Allow"] and "POST" not in res.headers["Allow"]
    assert _sha(db) == before


def test_the_route_is_registered_for_get_only(db):
    rule = [r for r in _app(db).url_map.iter_rules() if r.rule == API]
    assert len(rule) == 1 and (rule[0].methods - {"HEAD", "OPTIONS"}) == {"GET"}


# ---------------------------------------------------------------- what the body must not contain

def test_the_body_holds_no_absolute_path_drive_letter_tmp_path_env_text_or_token(db, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "TOKEN-SENTINEL-8f3a")
    _populate(db)
    text = json.dumps(_body(db))
    assert not re.search(r"[A-Za-z]:[\\/]", text) and "\\\\" not in text
    for forbidden in (str(db), str(db.parent), db.parent.name, "AppData", "Users", "/tmp", "pytest-of", ".env", "TOKEN-SENTINEL-8f3a",
                      "access_token", "Bearer"):
        assert forbidden not in text, forbidden
    f9 = _rows(_body(db))["F9"]
    assert f9["value"] and db.name in json.dumps(f9)                                         # the bare file name only


def test_there_is_no_merged_total_key_and_the_two_layers_stay_apart(db):
    _populate(db)
    keys = {k.lower() for k in _keys(_body(db))}
    assert not [k for k in keys if k in ("total", "combined", "merged", "grand_total", "overall", "sum", "all_layers")]
    assert {"scanrun", "e4"} <= keys


def test_scoring_stays_blocked_and_f8_is_never_ok(db):
    _populate(db)
    body = _body(db)
    assert body["scoring_status"] == "BLOCKED_B2"
    rows = _rows(body)
    assert rows["F8a"]["state"] != "OK" and rows["F8b"]["state"] != "OK"
    assert not [k for k in _keys(body) if k.lower() in ("score", "scores", "rank", "ranks", "target", "stop_loss", "recommendation")]


def test_no_raw_reason_or_abort_reason_key_and_no_hostile_text_anywhere(db):
    hostile = "INTERRUPTED: KeyboardInterrupt: Bearer SECRET123 https://x.example/?access_token=SECRET123"
    _two_layer_db_with_reasons(db, ["https://x.example/?access_token=SECRET123", "auth failure (401)"],
                               ["acquisition REQUEST_FAILED: ProviderError: Bearer SECRET123", "40 bars; 252 required"])
    _make_run(db, "a1", "2026-10-07T09:00:00", end="ABORTED", abort_reason=hostile)
    body = _body(db, datetime(2026, 10, 2, 12, 0, 0))
    text = json.dumps(body)
    for secret in ("SECRET123", "Bearer", "https://", "access_token", "ProviderError", "KeyboardInterrupt"):
        assert secret not in text, secret
    keys = set(_keys(body))
    assert not keys & {"reason", "status_reason", "scanrun_reason", "e4_reason", "abort_reason", "failure_reason", "errors_json"}
    assert {"scanrun_reason_code", "e4_reason_code"} <= keys and body["layer_disagreements"]["rows"]


# ---------------------------------------------------------------- demo mode

def test_demo_mode_builds_a_full_panel(tmp_path, monkeypatch):
    from scripts import dashboard_demo_seed as seed
    canonical, demo = tmp_path / "equity_intel.db", tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", canonical)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    seed.seed_demo_database(demo)
    app = create_app(demo=True)                                    # no db_path: the demo database path comes from db_path_guard
    app.config["HEALTH_CLOCK"] = lambda: datetime(2026, 9, 26, 12, 0, 0)
    body = app.test_client().get(API).get_json()
    assert body["demo"] is True and body["layers"]["scanrun"]["run_id"] == "r-demo-latest-complete" and body["layers"]["e4"]["scan_id"] == "demo-e4-2"
    assert [r["id"] for r in body["freshness"]] == ["F1", "F2", "F3", "F4a", "F4b", "F5", "F6", "F7", "F8a", "F8b", "F9"]
    assert _rows(body)["F1"]["state"] == "OK" and "DEMO_INDEX" in _rows(body)["F4b"]["value"]


# ---------------------------------------------------------------- read-only behaviour

def test_requests_leave_the_database_file_byte_identical(db):
    _populate(db)
    before = _sha(db)
    client = _app(db).test_client()
    for _ in range(3):
        assert client.get(API).status_code == 200
    assert client.post(API).status_code == 405 and client.get("/api/equity/summary").status_code == 200
    assert _sha(db) == before


def test_the_connection_the_route_hands_to_the_builder_cannot_write(db, monkeypatch):
    _populate(db)
    outcomes = []

    def probe(conn, now, info=None):
        for sql in ("INSERT INTO scan_runs (run_id, started_at, status, scoring_status) VALUES ('x', 'x', 'RUNNING', 'BLOCKED_B2')",
                    "UPDATE scan_runs SET status = 'ABORTED'", "DELETE FROM scan_runs", "CREATE TABLE evil (a)"):
            try:
                conn.execute(sql)
                outcomes.append("WROTE")
            except sqlite3.OperationalError as exc:
                outcomes.append(str(exc))
        return {"probe": True}

    monkeypatch.setattr(health, "build", probe)
    before = _sha(db)
    assert _app(db).test_client().get(API).get_json() == {"demo": False, "probe": True}
    assert len(outcomes) == 4 and "WROTE" not in outcomes and all("readonly" in o.lower() for o in outcomes)
    assert _sha(db) == before


def test_the_route_passes_the_builder_the_configured_file_and_never_an_absolute_path(db, monkeypatch):
    _populate(db)
    seen = {}

    def probe(conn, now, info=None):
        seen.update(info=info, now=now)
        return {}

    monkeypatch.setattr(health, "build", probe)
    _app(db).test_client().get(API)
    assert seen["info"] == health.read_db_file_info(db) and seen["now"] == NOW
    assert seen["info"]["name"] == db.name and set(seen["info"]) == {"name", "size_bytes", "modified_at"}

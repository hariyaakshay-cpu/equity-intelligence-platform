"""Tests for the Phase 4 read-only dashboard (dashboard/app.py, dashboard/queries.py).

Every fixture database is built through the normal scan_run lifecycle
(insert RUNNING, add results/snapshots, update to COMPLETE/ABORTED) via
equity_intel.persistence.connection -- exactly like real scanner code
would write it -- never by poking rows into a bare :memory: connection.
db_path_guard.CANONICAL_DB_PATH is monkeypatched to a tmp_path location for
every test, same pattern as equity_intel/tests/test_connection.py.
"""
import json
import socket
import sqlite3

import pytest

from dashboard import queries
from dashboard.app import DEFAULT_PORT, _build_arg_parser, _port_is_in_use, create_app
from equity_intel.persistence import connection, db_path_guard
from equity_intel.persistence.schema import SCHEMA_VERSION


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    return path


_SYMBOLS = [
    # symbol, company, sector, status, reason, history_gaps, corp_action, price_break, non_eq
    ("AAA", "Alpha Co", "IT", "VALID", None, 0, 0, 0, 0),
    ("BBB", "Bravo Co", "IT", "FAILED", "provider error", 1, 1, 0, 0),
    ("CCC", "Charlie Co", "Banking", "STALE", "stale data", 0, 0, 0, 0),
]


def _build_fixture_db(path, *, latest_started_at="2026-09-27T09:00:00", latest_closed_session="2026-09-25"):
    conn = connection.get_connection(path)
    try:
        connection.initialize_schema(conn)

        conn.execute(
            "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
            "VALUES ('r1', ?, 'RUNNING', 'BLOCKED_B2')",
            (latest_started_at,),
        )
        for symbol, name, sector, status, reason, hg, car, pbd, nes in _SYMBOLS:
            conn.execute(
                """
                INSERT INTO symbol_scan_results
                    (scan_run_id, symbol, company_name, sector, symbol_data_status, status_reason,
                     history_gaps_flag, corporate_action_review_flag, price_break_detected_flag, non_eq_series_flag)
                VALUES ('r1', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, name, sector, status, reason, hg, car, pbd, nes),
            )
            conn.execute(
                """
                INSERT INTO price_fetch_snapshots
                    (scan_run_id, symbol, trading_date, source, fetched_at_ist,
                     open, high, low, close, volume, content_hash, candle_validation_status)
                VALUES ('r1', ?, '2026-09-25', 'test', '2026-09-25T18:00:00+05:30',
                        '99', '101', '98', '100', 1000, ?, 'VALID')
                """,
                (symbol, f"hash-{symbol}"),
            )
        conn.execute(
            """
            UPDATE scan_runs
            SET status = 'COMPLETE', finished_at = ?, latest_closed_session = ?,
                universe_version = 'u', corporate_action_review_version = 'c',
                calendar_source = 'test-cal', calendar_verification = 'UNVERIFIED_INDEX_ONLY',
                requested_symbols = 3, successful_symbols = 1, failed_symbols = 1,
                status_counts_json = ?, flag_counts_json = ?
            WHERE run_id = 'r1'
            """,
            (
                latest_started_at,
                latest_closed_session,
                json.dumps({"VALID": 1, "INSUFFICIENT_HISTORY": 0, "STALE": 1, "FAILED": 1}),
                json.dumps(
                    {"history_gaps": 1, "corporate_action_review": 1, "price_break_detected": 0, "non_eq_series": 0}
                ),
            ),
        )
        conn.commit()

        conn.execute(
            "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
            "VALUES ('r2', '2026-09-26T09:00:00', 'RUNNING', 'BLOCKED_B2')"
        )
        conn.commit()
        conn.execute(
            "UPDATE scan_runs SET status = 'ABORTED', finished_at = '2026-09-26T09:05:00', "
            "abort_reason = 'calendar unavailable' WHERE run_id = 'r2'"
        )
        conn.commit()

        conn.execute(
            "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
            "VALUES ('r3', '2020-01-01T00:00:00', 'RUNNING', 'BLOCKED_B2')"
        )
        conn.commit()
    finally:
        conn.close()


def test_summary_reports_the_latest_complete_run(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/summary").get_json()
    assert data["run"]["run_id"] == "r1"
    assert data["run"]["scoring_status"] == "BLOCKED_B2"


def test_summary_reports_no_run_when_none_is_complete(db_path):
    conn = connection.get_connection(db_path)
    try:
        connection.initialize_schema(conn)
    finally:
        conn.close()
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/summary").get_json()
    assert data["run"] is None


def test_summary_flags_outdated_when_the_latest_closed_session_is_old(db_path):
    _build_fixture_db(db_path, latest_closed_session="2000-01-01")
    client = create_app(demo=False, db_path=db_path).test_client()
    assert client.get("/api/equity/summary").get_json()["outdated"] is True


def test_summary_is_not_outdated_when_the_latest_closed_session_is_current(db_path):
    today = queries.now_ist_naive().date().isoformat()
    _build_fixture_db(db_path, latest_closed_session=today)
    client = create_app(demo=False, db_path=db_path).test_client()
    assert client.get("/api/equity/summary").get_json()["outdated"] is False


def _add_smoke_run(path, *, run_id="r4", started_at="2026-09-28T09:00:00"):
    """A COMPLETE --symbols smoke run, more recent than r1's full run --
    must never outrank it as "the latest COMPLETE run"."""
    conn = connection.get_connection(path)
    try:
        conn.execute(
            "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
            "VALUES (?, ?, 'RUNNING', 'BLOCKED_B2')",
            (run_id, started_at),
        )
        conn.commit()
        conn.execute(
            """
            UPDATE scan_runs SET status = 'COMPLETE', finished_at = ?, latest_closed_session = '2026-09-25',
                universe_version = 'u', corporate_action_review_version = 'c',
                symbols_filter_json = ?
            WHERE run_id = ?
            """,
            (started_at, json.dumps(["INFY", "TCS"]), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_summary_never_reports_a_smoke_run_as_the_latest_complete_run(db_path):
    _build_fixture_db(db_path)
    _add_smoke_run(db_path)  # more recent than r1, but a smoke run
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/summary").get_json()
    assert data["run"]["run_id"] == "r1"


def test_scan_history_labels_a_smoke_run_and_a_full_run_differently(db_path):
    _build_fixture_db(db_path)
    _add_smoke_run(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/scan-history").get_json()
    by_id = {r["run_id"]: r for r in data["runs"]}
    assert by_id["r4"]["scan_label"] == "SMOKE (2 symbols)"
    assert by_id["r1"]["scan_label"] == "FULL"


def test_candidates_reports_blocked_b2_and_no_ranking(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/candidates").get_json()
    assert data["scoring_status"] == "BLOCKED_B2"
    assert data["total"] == 3
    for row in data["results"]:
        assert "rank" not in row
        assert "composite" not in row


def test_candidates_pagination(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    first = client.get("/api/equity/candidates?page=1&page_size=2").get_json()
    second = client.get("/api/equity/candidates?page=2&page_size=2").get_json()
    assert first["total"] == 3
    assert first["total_pages"] == 2
    assert [r["symbol"] for r in first["results"]] == ["AAA", "BBB"]
    assert [r["symbol"] for r in second["results"]] == ["CCC"]


def test_candidates_filters_by_status(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/candidates?status=FAILED").get_json()
    assert [r["symbol"] for r in data["results"]] == ["BBB"]


def test_candidates_filters_by_flag(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/candidates?flag=history_gaps").get_json()
    assert [r["symbol"] for r in data["results"]] == ["BBB"]


def test_candidates_search_by_symbol_or_company(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/candidates?q=charlie").get_json()
    assert [r["symbol"] for r in data["results"]] == ["CCC"]


def test_candidates_rejects_an_unknown_status_filter(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    res = client.get("/api/equity/candidates?status=BOGUS")
    assert res.status_code == 400


def test_sectors_groups_by_sector_and_status(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/sectors").get_json()
    by_sector = {s["sector"]: s for s in data["sectors"]}
    assert by_sector["IT"]["total"] == 2
    assert by_sector["Banking"]["total"] == 1


def test_stock_endpoint_returns_candles_and_fetch_history(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/stock/AAA").get_json()
    assert data["result"]["symbol_data_status"] == "VALID"
    assert len(data["candles"]) == 1
    assert data["candles"][0]["trading_date"] == "2026-09-25"
    assert len(data["fetch_history"]) == 1


def test_stock_endpoint_404_for_unknown_symbol(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    assert client.get("/api/equity/stock/NOPE").status_code == 404


def test_scan_history_includes_all_run_statuses(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/scan-history").get_json()
    statuses = {r["run_id"]: r["status"] for r in data["runs"]}
    assert statuses == {"r1": "COMPLETE", "r2": "ABORTED", "r3": "RUNNING"}
    aborted = next(r for r in data["runs"] if r["run_id"] == "r2")
    assert aborted["abort_reason"] == "calendar unavailable"


def test_scan_history_flags_a_stale_running_run_display_only(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    data = client.get("/api/equity/scan-history").get_json()
    by_id = {r["run_id"]: r for r in data["runs"]}
    assert by_id["r3"]["running_stale_warning"] is True
    # A COMPLETE/ABORTED run is never flagged "running stale", regardless of age.
    assert by_id["r1"]["running_stale_warning"] is False
    assert by_id["r2"]["running_stale_warning"] is False


def test_demo_banner_shown_only_in_demo_mode(db_path):
    _build_fixture_db(db_path)
    real_client = create_app(demo=False, db_path=db_path).test_client()
    demo_client = create_app(demo=True, db_path=db_path).test_client()
    assert b"DEMO DATA" not in real_client.get("/equity").data
    assert b"DEMO DATA" in demo_client.get("/equity").data


def test_dashboard_connection_is_read_only(db_path):
    _build_fixture_db(db_path)
    conn = connection.get_read_only_connection(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
                "VALUES ('x', 'x', 'RUNNING', 'BLOCKED_B2')"
            )
    finally:
        conn.close()


def test_every_api_route_returns_200_and_no_scans_yet_for_a_missing_db(db_path):
    # db_path is monkeypatched but never created/initialized by this test.
    client = create_app(demo=False, db_path=db_path).test_client()
    for path in (
        "/api/equity/summary",
        "/api/equity/candidates",
        "/api/equity/sectors",
        "/api/equity/stock/AAA",
        "/api/equity/scan-history",
    ):
        res = client.get(path)
        assert res.status_code == 200, path
        data = res.get_json()
        assert data["status"] == "no_scans_yet"
        assert "no scans" in data["message"].lower()


def test_equity_page_shows_no_scans_yet_message_for_a_missing_db(db_path):
    client = create_app(demo=False, db_path=db_path).test_client()
    res = client.get("/equity")
    assert res.status_code == 200
    assert b"No scans have been recorded yet." in res.data


def test_every_api_route_returns_200_and_a_clear_message_on_version_mismatch(db_path):
    conn = connection.get_connection(db_path)
    try:
        connection.initialize_schema(conn)
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))
        conn.commit()
    finally:
        conn.close()

    client = create_app(demo=False, db_path=db_path).test_client()
    for path in (
        "/api/equity/summary",
        "/api/equity/candidates",
        "/api/equity/sectors",
        "/api/equity/stock/AAA",
        "/api/equity/scan-history",
    ):
        res = client.get(path)
        assert res.status_code == 200, path
        data = res.get_json()
        assert data["status"] == "version_mismatch"
        assert "version mismatch" in data["message"].lower()
        assert str(SCHEMA_VERSION + 1) in data["message"]


def test_equity_page_shows_version_mismatch_message(db_path):
    conn = connection.get_connection(db_path)
    try:
        connection.initialize_schema(conn)
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))
        conn.commit()
    finally:
        conn.close()

    client = create_app(demo=False, db_path=db_path).test_client()
    res = client.get("/equity")
    assert res.status_code == 200
    assert b"version mismatch" in res.data.lower()


def test_open_checked_connection_lets_a_guard_refused_path_raise(tmp_path):
    # A path db_path_guard doesn't recognize (neither the real
    # CANONICAL_DB_PATH nor DEMO_DB_PATH -- not monkeypatched here, so
    # any tmp_path is naturally forbidden) is a configuration bug, not a
    # routine "no data" state: it must fail loudly, never be swallowed
    # into a 200 "no scans yet" response.
    from dashboard.app import _open_checked_connection

    forbidden = tmp_path / "not_allowed.db"
    with pytest.raises(ValueError):
        _open_checked_connection(forbidden)


def test_open_checked_connection_reports_database_error_for_a_corrupt_file(db_path):
    from dashboard.app import _DatabaseError, _open_checked_connection

    db_path.write_bytes(b"\x00\x01this is not a sqlite database\xff\xfe" * 50)
    with pytest.raises(_DatabaseError):
        _open_checked_connection(db_path)


def test_every_api_route_returns_200_and_database_error_for_a_corrupt_file(db_path):
    db_path.write_bytes(b"\x00\x01this is not a sqlite database\xff\xfe" * 50)
    client = create_app(demo=False, db_path=db_path).test_client()
    for path in (
        "/api/equity/summary",
        "/api/equity/candidates",
        "/api/equity/sectors",
        "/api/equity/stock/AAA",
        "/api/equity/scan-history",
    ):
        res = client.get(path)
        assert res.status_code == 200, path
        data = res.get_json()
        assert data["status"] == "database_error"
        assert data["status"] != "no_scans_yet"


def test_equity_page_shows_database_error_message_for_a_corrupt_file(db_path):
    db_path.write_bytes(b"\x00\x01this is not a sqlite database\xff\xfe" * 50)
    client = create_app(demo=False, db_path=db_path).test_client()
    res = client.get("/equity")
    assert res.status_code == 200
    assert b"database error" in res.data.lower()
    assert b"no scans have been recorded yet" not in res.data.lower()


def test_no_dashboard_route_accepts_a_write_method(db_path):
    _build_fixture_db(db_path)
    client = create_app(demo=False, db_path=db_path).test_client()
    for path in (
        "/equity",
        "/api/equity/summary",
        "/api/equity/candidates",
        "/api/equity/sectors",
        "/api/equity/stock/AAA",
        "/api/equity/scan-history",
    ):
        assert client.post(path).status_code in (404, 405)


def test_default_port_is_5050_not_5000():
    # Port 5000 is already used by the algo_trader dashboard, which must
    # keep running -- this dashboard must never default to it.
    assert DEFAULT_PORT == 5050
    args = _build_arg_parser().parse_args([])
    assert args.port == 5050


def test_port_override_via_cli_flag():
    args = _build_arg_parser().parse_args(["--port", "5051"])
    assert args.port == 5051


def test_port_is_in_use_detects_a_bound_port():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    bound_port = server.getsockname()[1]
    try:
        assert _port_is_in_use("127.0.0.1", bound_port) is True
    finally:
        server.close()


def test_port_is_in_use_is_false_for_a_free_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()
    assert _port_is_in_use("127.0.0.1", free_port) is False


def test_main_exits_with_a_clear_error_when_the_port_is_already_in_use(monkeypatch, capsys):
    import dashboard.app as app_module

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    taken_port = server.getsockname()[1]
    try:
        monkeypatch.setattr(
            "sys.argv", ["dashboard_app", "--host", "127.0.0.1", "--port", str(taken_port)]
        )
        with pytest.raises(SystemExit) as exc_info:
            app_module.main()
        assert exc_info.value.code == 1
        assert f"port {taken_port}" in capsys.readouterr().err
    finally:
        server.close()


def test_main_prints_the_serving_url_before_running(monkeypatch, capsys):
    import dashboard.app as app_module

    monkeypatch.setattr(app_module, "_port_is_in_use", lambda host, port: False)
    monkeypatch.setattr("sys.argv", ["dashboard_app", "--host", "127.0.0.1", "--port", "5050"])

    def fake_run(self, host=None, port=None, **kwargs):
        # Stand in for Flask.run(): we only care that main() printed the
        # URL before attempting to serve, not that a real server started.
        pass

    monkeypatch.setattr("flask.Flask.run", fake_run)
    app_module.main()
    assert "http://127.0.0.1:5050/equity" in capsys.readouterr().out

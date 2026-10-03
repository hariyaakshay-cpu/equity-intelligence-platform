"""Stage 1 Stock Detail page (/equity/stock/<symbol>), exercised on the seeded demo database.

db_path_guard paths are monkeypatched to tmp_path, so the real
data/equity_intel*.db are never touched.
"""
import sqlite3

import pytest

from dashboard import stock_detail
from dashboard.app import BANNER_TEXT, create_app
from equity_intel.persistence import connection, db_path_guard
from scripts.dashboard_demo_seed import seed_demo_database

SYMBOLS = ["DEMOAAA", "DEMOAAC", "DEMOBAA", "DEMOPAB", "DEMOAUB", "DEMOFAB"]  # VALID, CA flag, break, STALE, INSUFF, FAILED


@pytest.fixture
def demo_db(monkeypatch, tmp_path):
    canonical, demo = tmp_path / "equity_intel.db", tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", canonical)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    seed_demo_database(demo)
    return demo


@pytest.fixture
def client(demo_db):
    return create_app(demo=True, db_path=demo_db).test_client()


def _page(client, symbol):
    res = client.get(f"/equity/stock/{symbol}")
    return res, res.get_data(as_text=True)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_stock_page_returns_200_on_demo_data(client, symbol):
    res, html = _page(client, symbol)
    assert res.status_code == 200
    assert symbol in html and "DEMO DATA - NOT REAL" in html


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_banner_text_on_stock_page(client, symbol):
    assert BANNER_TEXT in _page(client, symbol)[1]


def test_banner_text_on_404_and_on_the_original_equity_page(client):
    res, html = _page(client, "NOPE")
    assert res.status_code == 404 and BANNER_TEXT in html
    assert BANNER_TEXT in client.get("/equity").get_data(as_text=True)


def test_unknown_symbol_is_a_404_page_not_a_stack_trace(client):
    res, html = _page(client, "NOPE")
    assert res.status_code == 404
    assert "Symbol not found" in html and "Traceback" not in html
    assert res.mimetype == "text/html"


def test_missing_database_is_a_message_page_not_a_500(monkeypatch, tmp_path):
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", tmp_path / "equity_intel.db")
    res = create_app(demo=False).test_client().get("/equity/stock/AAA")
    html = res.get_data(as_text=True)
    assert res.status_code == 200 and "No scans yet" in html and BANNER_TEXT in html


def test_connection_is_read_only_a_write_attempt_fails(demo_db):
    conn = connection.get_read_only_connection(demo_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE symbol_scan_results SET sector = 'X'")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE should_not_exist (x)")
    finally:
        conn.close()


def test_only_get_is_allowed_on_the_stock_route(client):
    assert client.post("/equity/stock/DEMOAAA").status_code == 405


def test_valid_symbol_shows_checks_e4_provenance_and_history(client):
    html = _page(client, "DEMOAAA")[1]
    for section in ("Data status checks", "E4 data", "Data provenance", "Status history", "Corporate-action / data flags"):
        assert section in html
    assert "VALID" in html and "252 sessions" in html
    assert "EMA50" in html and "EMA200" in html and "52W high" in html
    assert "r-demo-latest-complete" in html and "r-demo-prev-complete" in html  # one history row per run
    assert "per-symbol check" in html and "reproduce their stored hash" in html
    assert "DEMO fabricated series" in html  # adjustment basis comes from the stored rows


def test_52_week_low_is_not_recorded_and_failed_symbol_shows_not_recorded_everywhere(client):
    html = _page(client, "DEMOAAA")[1]
    assert "E4 does not store a 52-week low" in html
    failed = _page(client, "DEMOFAB")[1]
    assert "FAILED" in failed and "not recorded" in failed and "no COMPLETE E4 scan" not in failed
    assert "no E4 row for this symbol" in failed


def test_layers_are_labelled(client):
    html = _page(client, "DEMOAAA")[1]
    assert "layer-ScanRun" in html and "layer-E4" in html and "provisional" in html


def test_volume_rule_is_marked_not_frozen(client):
    assert "rule not frozen" in _page(client, "DEMOAAA")[1]


def test_newer_smoke_run_is_named_with_reason_and_symbol_count(client):
    html = _page(client, "DEMOAAA")[1]
    assert "A newer non-complete run exists" in html
    assert "r-demo-smoke" in html and "smoke run (--symbols, 2 symbols)" in html
    assert "r-demo-latest-complete" in html  # still showing the last COMPLETE full run


def test_newer_aborted_and_running_runs_are_reported(demo_db):
    conn = connection.get_connection(demo_db)
    try:
        conn.execute("INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
                     "VALUES ('r-new-abort', '2026-09-29T10:00:00', 'RUNNING', 'BLOCKED_B2')")
        conn.execute("UPDATE scan_runs SET status='ABORTED', abort_reason='AUTH_FAILED', requested_symbols=500 "
                     "WHERE run_id='r-new-abort'")
        conn.commit()
    finally:
        conn.close()
    ro = connection.get_read_only_connection(demo_db)
    try:
        run = {"started_at": "2026-09-28T10:00:00"}
        aborted = stock_detail.get_newer_non_complete_run(ro, run)
    finally:
        ro.close()
    assert aborted["run_id"] == "r-new-abort"
    assert "ABORTED (AUTH_FAILED)" in aborted["reason"] and "500 symbols requested" in aborted["symbols"]

    conn = connection.get_connection(demo_db)
    try:
        conn.execute("INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
                     "VALUES ('r-new-run', '2026-09-30T10:00:00', 'RUNNING', 'BLOCKED_B2')")
        conn.commit()
    finally:
        conn.close()
    ro = connection.get_read_only_connection(demo_db)
    try:
        running = stock_detail.get_newer_non_complete_run(ro, {"started_at": "2026-09-28T10:00:00"})
        none = stock_detail.get_newer_non_complete_run(ro, {"started_at": "2026-10-01T00:00:00"})
    finally:
        ro.close()
    assert running["run_id"] == "r-new-run" and "RUNNING" in running["reason"]
    assert "requested symbol count not recorded" in running["symbols"]
    assert none is None


def test_hash_mismatch_is_reported_per_symbol(client, monkeypatch):
    monkeypatch.setattr(stock_detail, "compute_content_hash_from_stored_row", lambda row: "0" * 64)
    html = _page(client, "DEMOAAA")[1]
    assert "do not reproduce their stored hash" in html


def test_page_has_no_score_rank_signal_or_action_controls(client):
    html = _page(client, "DEMOAAA")[1].lower()
    for word in ("buy", "sell", "rank", "confidence", "<form", "<button", "mark reviewed", "<canvas", "<svg"):
        assert word not in html


@pytest.fixture
def real_mode_client(demo_db):
    # demo=False so the review CSV on disk is consulted (the DB is the seeded fixture).
    return create_app(demo=False, db_path=demo_db).test_client()


HEADER = "symbol,isin,event_type,effective_date,reason,reviewer,review_state\n"


def test_empty_review_file_is_not_reported_as_no_corporate_actions(real_mode_client, monkeypatch, tmp_path):
    csv = tmp_path / "review.csv"
    csv.write_text(HEADER, encoding="utf-8")
    monkeypatch.setattr(stock_detail, "review_csv_path", lambda: csv)
    html = _page(real_mode_client, "DEMOAAC")[1]
    assert "review file empty: no symbols reviewed" in html
    assert "no corporate actions" not in html.lower()


def test_missing_review_file_is_reported_as_unavailable(real_mode_client, monkeypatch, tmp_path):
    monkeypatch.setattr(stock_detail, "review_csv_path", lambda: tmp_path / "absent.csv")
    html = _page(real_mode_client, "DEMOAAC")[1]
    assert "review file unavailable" in html


def test_review_entry_for_the_symbol_is_listed_read_only(real_mode_client, monkeypatch, tmp_path):
    csv = tmp_path / "review.csv"
    csv.write_text(HEADER + "DEMOAAC,,SPLIT,2026-09-10,face value split,akshay,UNREVIEWED\n"
                            "OTHER,,BONUS,2026-09-11,x,akshay,UNREVIEWED\n", encoding="utf-8")
    monkeypatch.setattr(stock_detail, "review_csv_path", lambda: csv)
    html = _page(real_mode_client, "DEMOAAC")[1]
    assert "SPLIT" in html and "2026-09-10" in html and "face value split" in html and "OTHER" not in html
    # the review file differs from the version the (demo) run recorded: say so
    assert "differs from the version this run used" in html


def test_demo_mode_does_not_read_the_review_file(client):
    assert "not read in demo mode" in _page(client, "DEMOAAC")[1]

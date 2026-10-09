"""Phase 1 gap fixes on the Stock Detail page: header identifiers, OHLCV table, E4 labels,
stored-row integrity, adjustment NOT_DEFINED.

Reuses the demo fixtures of test_dashboard_stock_page.py (tmp_path databases only).
"""
import re
from datetime import date, timedelta

from dashboard import queries, stock_detail
from equity_intel.persistence import connection
from equity_intel.scanner import classification
from equity_intel.tests.test_dashboard_stock_page import _page, client, demo_db  # noqa: F401  (fixtures)
from scripts import dashboard_demo_seed as seed


def _identifiers(html):
    return html.split('id="identifiers"')[1].split("</div>")[0]


def test_header_shows_instrument_key_isin_and_series(client, monkeypatch):
    # finished runs are immutable (schema trigger), so inject the stored identifiers at the query helper
    real = queries.get_symbol_result
    monkeypatch.setattr(queries, "get_symbol_result", lambda conn, run_id, symbol: {
        **real(conn, run_id, symbol), "instrument_key": "NSE_EQ|INE000A00001", "isin": "INE000A00001", "series": "EQ"})
    ident = _identifiers(_page(client, "DEMOAAA")[1])
    assert "NSE_EQ|INE000A00001" in ident and "INE000A00001" in ident and "<code>EQ</code>" in ident
    assert "instrument key" in ident and "ISIN" in ident and "series" in ident


def test_header_identifiers_missing_values_render_not_recorded(client):
    ident = _identifiers(_page(client, "DEMOAAA")[1])
    assert ident.count("not recorded") == 3 and "None" not in ident


def test_failed_symbol_header_identifiers_are_not_recorded_not_zero(client):
    ident = _identifiers(_page(client, "DEMOFAB")[1])
    assert ident.count("not recorded") == 3 and ">0<" not in ident


def _ohlcv_dates(html):
    section = html.split('id="ohlcv"')[1].split('id="history"')[0]
    return re.findall(r"<tr><td>(\d{4}-\d{2}-\d{2})</td>", section)


def test_ohlcv_table_shows_the_stored_bars_newest_first(client):
    html = _page(client, "DEMOAAA")[1]
    assert _ohlcv_dates(html) == ["2026-09-25", "2026-09-24", "2026-09-23"]
    assert "Open</th>" in html and "Volume</th>" in html
    note = html.split('id="ohlcv"')[1].split("</p>")[0]
    assert ("Stored values as retrieved from the vendor. The dashboard does not adjust or compute them; "
            "whether the vendor adjusted them is NOT_DEFINED (see adjustment basis).") in note
    assert "nothing here is adjusted" not in html


def test_ohlcv_table_is_capped_at_ohlcv_rows_newest_first(demo_db):
    # 45 bars in a fresh (unfinished) run: only the newest OHLCV_ROWS are returned, newest first.
    assert stock_detail.OHLCV_ROWS == 30
    conn = connection.get_connection(demo_db)
    try:
        seed._insert_scan_run(conn, "r-long", "2026-10-01T10:00:00")
        seed._insert_symbol_result(conn, "r-long", "LONGSYM", "Long Co", "IT", "VALID", None, {
            "history_gaps": False, "corporate_action_review": False, "price_break_detected": False, "non_eq_series": False})
        first = date(2026, 6, 1)
        for i in range(45):
            seed._insert_snapshot(conn, "r-long", "LONGSYM", (first + timedelta(days=i)).isoformat(), "2026-10-01T10:00:00", 100.0 + i)
        conn.commit()
    finally:
        conn.close()
    ro = connection.get_read_only_connection(demo_db)
    try:
        run = queries.get_run(ro, "r-long")
        context = stock_detail.build(ro, run, "LONGSYM", queries.get_symbol_result(ro, "r-long", "LONGSYM"), True)
    finally:
        ro.close()
    dates = [b["trading_date"] for b in context["ohlcv"]]
    assert len(dates) == 30 and dates[0] == "2026-07-15" and dates[-1] == "2026-06-16"
    assert dates == sorted(dates, reverse=True)


def test_failed_symbol_ohlcv_is_not_recorded_not_an_empty_zero_table(client):
    section = _page(client, "DEMOFAB")[1].split('id="ohlcv"')[1].split('id="history"')[0]
    assert "not recorded" in section and "no bars are stored" in section and "<table>" not in section


def test_ohlcv_card_has_no_chart_element(client):
    section = _page(client, "DEMOAAA")[1].split('id="ohlcv"')[1].split('id="history"')[0].lower()
    for tag in ("<canvas", "<svg", "<img", "<script"):
        assert tag not in section


def _e4_card(html):
    return html.split('id="e4"')[1].split('id="provenance"')[0]


def test_e4_card_says_raw_value_not_a_score_with_run_id_and_as_of(client):
    card = _e4_card(_page(client, "DEMOAAA")[1])
    assert "raw value, not a score" in card
    assert "E4 scan <code>" in card and "as of 2026-" in card


def test_rsi_roc_atr_are_the_stored_e4_values_not_computed(client, demo_db):
    conn = connection.get_read_only_connection(demo_db)
    try:
        rsi, roc, atr = conn.execute(
            "SELECT f.rsi, f.roc, f.atr_percent FROM e4_feature_sets f WHERE f.symbol = 'DEMOAAA' "
            "AND f.scan_id = (SELECT scan_id FROM e4_scan_runs WHERE status = 'COMPLETE' ORDER BY started_at DESC LIMIT 1)"
        ).fetchone()
    finally:
        conn.close()
    assert None not in (rsi, roc, atr)
    card = _e4_card(_page(client, "DEMOAAA")[1])
    for label, stored in (("RSI", rsi), ("ROC", roc), ("ATR %", atr)):
        row = re.search(r"<th>" + re.escape(label) + r"</th><td class=\"num\">(.*?)</td>", card).group(1)
        assert row == f"{stored:.2f}", label


def test_failed_symbol_rsi_roc_atr_are_not_recorded_not_zero(client):
    card = _e4_card(_page(client, "DEMOFAB")[1])
    for label in ("RSI", "ROC", "ATR %"):
        row = re.search(r"<th>" + re.escape(label) + r"</th><td class=\"num\">(.*?)</td>", card).group(1)
        assert "not recorded" in row and "0.00" not in row, label


def _hash_state(html):
    return re.search(r'id="hash-state"[^>]*>(.*?)</span>', html, re.S).group(1)


def test_stored_row_integrity_match(client):
    html = _page(client, "DEMOAAA")[1]
    assert "stored-row integrity:" in html and _hash_state(html) == "MATCH"


def test_stored_row_integrity_mismatch(client, monkeypatch):
    monkeypatch.setattr(stock_detail, "compute_content_hash_from_stored_row", lambda row: "0" * 64)
    html = _page(client, "DEMOAAA")[1]
    assert _hash_state(html) == "MISMATCH" and "3 of 3 stored bars do not reproduce their stored hash" in html


def test_stored_row_integrity_unavailable_when_there_are_no_bars(client):
    # a FAILED symbol has no stored bars: UNAVAILABLE, never MATCH
    html = _page(client, "DEMOFAB")[1]
    assert _hash_state(html) == "UNAVAILABLE" and "MATCH" not in html.replace("MISMATCH", "")


def test_stored_row_integrity_note_says_it_does_not_prove_vendor_data_unchanged(client):
    note = _page(client, "DEMOAAA")[1].split('id="hash-note"')[1].split("</div>")[0]
    assert ("Checks that stored bars match their stored hash. It does not prove the vendor data is unchanged; "
            "vendor revisions are detected by the Snapshot Audit compare.") in note


def test_adjustment_basis_is_always_the_literal_not_defined_with_the_stored_value_as_a_note(client):
    html = _page(client, "DEMOAAA")[1]
    assert re.search(r'id="adjustment-status">NOT_DEFINED</span>', html)
    note = html.split('id="adjustment-stored"')[1].split("</span>")[0]
    assert "DEMO fabricated series (not a real adjustment basis)" in note


def test_adjustment_basis_is_not_defined_even_when_nothing_is_stored(client):
    html = _page(client, "DEMOFAB")[1]  # FAILED: no E4 acquisition rows
    assert re.search(r'id="adjustment-status">NOT_DEFINED</span>', html)
    assert "not recorded" in html.split('id="adjustment-stored"')[1].split("</span>")[0]


def test_stock_page_still_has_no_chart_score_or_signal_wording(client):
    for symbol in ("DEMOAAA", "DEMOFAB"):
        html = _page(client, symbol)[1].lower()
        for word in ("<canvas", "<svg", "buy", "sell", "rank", "confidence", "target", "stop-loss", "<form", "<button"):
            assert word not in html, (symbol, word)


def _run_main(monkeypatch, capsys, argv):
    from dashboard import app as dashboard_app
    served = {}
    monkeypatch.setattr("sys.argv", ["dashboard.app", *argv])
    monkeypatch.setattr(dashboard_app, "_port_is_in_use", lambda host, port: False)
    monkeypatch.setattr(dashboard_app.Flask, "run", lambda self, **kw: served.update(db=self.config["DB_PATH"], **kw))
    dashboard_app.main()
    return capsys.readouterr().out, served


def test_demo_startup_prints_demo_mode_and_selects_the_demo_db(monkeypatch, capsys):
    out, served = _run_main(monkeypatch, capsys, ["--demo"])
    assert "DEMO MODE - using data/equity_intel_demo.db" in out
    assert str(served["db"]).endswith("equity_intel_demo.db") and served["port"] == 5050


def test_non_demo_startup_prints_no_demo_line_and_selects_the_real_db(monkeypatch, capsys):
    out, served = _run_main(monkeypatch, capsys, [])
    assert "DEMO MODE" not in out and "Serving equity_intel dashboard at" in out
    assert str(served["db"]).endswith("equity_intel.db") and "demo" not in str(served["db"])


def test_header_identifiers_flow_from_the_scanner_writer_to_the_page(client, demo_db):
    # Real data flow, no monkeypatching: the scanner's own writer stores the row in a RUNNING run, the run
    # completes, and the real route (queries.get_symbol_result -> stock_detail.build -> template) renders it.
    conn = connection.get_connection(demo_db)
    try:
        seed._insert_scan_run(conn, "r-real-flow", "2026-10-02T09:20:00")
        for symbol, key in (("REALSYM", "NSE_EQ|INE000A00001"), ("NOKEYSYM", None)):  # None: ISIN unmapped
            classification.write_symbol_scan_result(
                conn, scan_run_id="r-real-flow", symbol=symbol, instrument_key=key, isin="INE000A00001",
                series="EQ", company_name="Real Co", sector="IT", symbol_data_status="VALID", status_reason=None,
                available_session_count=252, missing_session_count=0)
            seed._insert_snapshot(conn, "r-real-flow", symbol, "2026-10-01", "2026-10-02T09:20:00+05:30", 100.0)
        seed._complete_run(conn, "r-real-flow", "2026-10-02T09:45:00", "2026-10-01",
                           {"VALID": 2, "INSUFFICIENT_HISTORY": 0, "STALE": 0, "FAILED": 0},
                           {"history_gaps": 0, "corporate_action_review": 0, "price_break_detected": 0, "non_eq_series": 0},
                           requested=2, successful=2, failed=0)
        conn.commit()
    finally:
        conn.close()
    ident = _identifiers(_page(client, "REALSYM")[1])
    assert "r-real-flow" in _page(client, "REALSYM")[1]
    assert "<code>NSE_EQ|INE000A00001</code>" in ident and "<code>INE000A00001</code>" in ident and "<code>EQ</code>" in ident
    # an unmapped ISIN stores a NULL instrument key: shown as not recorded, ISIN and series still shown
    unmapped = _identifiers(_page(client, "NOKEYSYM")[1])
    assert "not recorded" in unmapped.split("ISIN")[0] and "<code>INE000A00001</code>" in unmapped

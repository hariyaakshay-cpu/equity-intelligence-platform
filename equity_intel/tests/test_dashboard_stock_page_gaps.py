"""Phase 1 gap fixes on the Stock Detail page: header identifiers, OHLCV table, E4 labels,
stored-row integrity, adjustment NOT_DEFINED.

Reuses the demo fixtures of test_dashboard_stock_page.py (tmp_path databases only).
"""
import re
from datetime import date, timedelta

from dashboard import queries, stock_detail
from equity_intel.persistence import connection
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
    assert "Open</th>" in html and "Volume</th>" in html and "nothing here is adjusted or computed" in html


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

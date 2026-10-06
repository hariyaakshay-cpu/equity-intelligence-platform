"""Phase 1 gap fixes on the Stock Detail page: header identifiers, OHLCV table, E4 labels,
stored-row integrity, adjustment NOT_DEFINED.

Reuses the demo fixtures of test_dashboard_stock_page.py (tmp_path databases only).
"""
from dashboard import queries
from equity_intel.tests.test_dashboard_stock_page import _page, client, demo_db  # noqa: F401  (fixtures)


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

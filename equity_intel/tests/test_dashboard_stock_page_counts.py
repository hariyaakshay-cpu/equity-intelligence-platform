"""The Stock Detail page's 252-session check is the STORED available_session_count, never a count of
snapshot rows, and a FAILED symbol is never shown as met or not met.

Reuses the demo fixtures of test_dashboard_stock_page.py.
"""
import re

from dashboard import stock_detail
from equity_intel.persistence import connection
from equity_intel.tests.test_dashboard_stock_page import _page, client, demo_db  # noqa: F401  (fixtures)

GLYPH_ENTITIES = ("&#10003;", "&#10007;")


def _state(row):
    """The check-state word of a checks row: met, not met or not evaluated."""
    return re.search(r'<span class="[a-z]+ check-state">([^<]*)</span>', row).group(1)


def _row(html, label):
    """The <tr> whose first cell is `label`, as a string."""
    return re.search(r"<tr>\s*<td>" + re.escape(label) + r"</td>.*?</tr>", html, re.S).group(0)


def _cell(html, label):
    return re.search(r"<th>" + re.escape(label) + r"</th>(.*?)</tr>", html, re.S).group(1)


def _query(demo_db, sql, params=()):
    conn = connection.get_read_only_connection(demo_db)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_sessions_check_is_the_stored_count_not_the_number_of_snapshot_rows(client, demo_db):
    stored, snapshots = _query(
        demo_db,
        "SELECT s.available_session_count, (SELECT COUNT(*) FROM price_fetch_snapshots p "
        "WHERE p.scan_run_id = s.scan_run_id AND p.symbol = s.symbol) "
        "FROM symbol_scan_results s WHERE s.scan_run_id = 'r-demo-latest-complete' AND s.symbol = 'DEMOAUB'")[0]
    assert (stored, snapshots) == (41, 3)  # they deliberately disagree
    html = _page(client, "DEMOAUB")[1]
    row = _row(html, "252 sessions")
    assert "41 of 252 available" in row and "3 of 252" not in row and _state(row) == "not met"
    assert not any(g in row for g in GLYPH_ENTITIES)
    assert "<td>3 (" in _cell(html, "Bars retrieved") or "3 (2026-09-23" in _cell(html, "Bars retrieved")


def test_failed_symbol_is_not_applicable_with_no_met_or_not_met_and_nothing_recorded(client):
    html = _page(client, "DEMOFAB")[1]
    row = _row(html, "252 sessions")
    assert "not applicable: acquisition failed" in row and "stored count: not recorded" in row
    for check in ("252 sessions", "Corporate-action review flag", "Price-break flag"):
        assert _state(_row(html, check)) == "not evaluated", check
        assert not any(g in _row(html, check) for g in GLYPH_ENTITIES), check
    assert "not recorded" in _cell(html, "Bars retrieved") and "2026" not in _cell(html, "Bars retrieved")
    assert "not recorded" in _cell(html, "Data-through date").split("(")[0]
    assert "not recorded" in _cell(html, "Retrieved at")
    assert 'id="status-badge">FAILED' in html


def test_demo_failed_rows_match_what_the_real_scanner_stores(demo_db):
    # scripts/equity_scan.py record_failed: NULL counts, no classification flags, and no snapshots
    # (a failed symbol's snapshot writes are rolled back, an unmapped ISIN is never fetched).
    rows = _query(demo_db, "SELECT symbol, available_session_count, missing_session_count, history_gaps_flag, "
                           "corporate_action_review_flag, price_break_detected_flag FROM symbol_scan_results "
                           "WHERE symbol_data_status = 'FAILED'")
    assert rows
    for symbol, available, missing, gaps, review, price_break in rows:
        assert (available, missing, gaps, review, price_break) == (None, None, 0, 0, 0), symbol
    assert _query(demo_db, "SELECT COUNT(*) FROM symbol_scan_results s WHERE s.symbol_data_status = 'FAILED' AND EXISTS "
                           "(SELECT 1 FROM price_fetch_snapshots p WHERE p.scan_run_id = s.scan_run_id AND p.symbol = s.symbol)"
                  )[0][0] == 0


def _checks(status, available, missing=None):
    result = {"symbol_data_status": status, "available_session_count": available, "missing_session_count": missing,
              "corporate_action_review_flag": 0, "price_break_detected_flag": 0}
    return {c["name"]: c for c in stock_detail._status_checks(result, {}, None, None, None)}


def test_a_null_count_renders_not_recorded_and_not_evaluated():
    check = _checks("VALID", None)["252 sessions"]
    assert check["result"] == "not recorded" and check["ok"] is None


def test_a_zero_count_is_handled_and_is_not_met():
    check = _checks("INSUFFICIENT_HISTORY", 0, 252)["252 sessions"]
    assert check["result"].startswith("0 of 252 available") and check["ok"] is False


def test_failed_with_a_stored_count_shows_it_as_stored_but_never_as_met():
    for stored in (0, 252):
        check = _checks("FAILED", stored)["252 sessions"]
        assert f"not applicable: acquisition failed (stored count: {stored} of 252)" == check["result"]
        assert check["ok"] is None
    assert all(c["ok"] is None for c in _checks("FAILED", 252).values())


def test_the_checks_column_states_met_not_met_or_not_evaluated_in_words_with_the_layer_tag(client):
    html = _page(client, "DEMOAAA")[1]
    states = {}
    for check in ("252 sessions", "Corporate-action review flag", "Price-break flag"):
        row = _row(html, check)
        states[check] = _state(row)
        assert "layer-ScanRun" in row, check
    assert states == {"252 sessions": "met", "Corporate-action review flag": "met", "Price-break flag": "met"}
    flagged = _row(_page(client, "DEMOX21")[1], "Price-break flag")
    assert _state(flagged) == "not met" and "FLAGGED" in flagged

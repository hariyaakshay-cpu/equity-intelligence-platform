"""GET /equity/exceptions (the HTML page): rendering, links, URL-persisted filters, escaping, empty states.

Runs are built per case in tmp_path databases by the helpers of test_dashboard_exceptions_api.py.
"""
import hashlib
import html as htmllib
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from dashboard import exceptions
from dashboard.app import BANNER_TEXT, create_app
from equity_intel.persistence import connection, db_path_guard
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_exceptions_api import CATEGORY_ROWS, EXPECTED, _marker_runs, _run
from scripts import dashboard_demo_seed as seed


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def _page(client, query=""):
    res = client.get("/equity/exceptions" + (("?" + query) if query else ""))
    return res, res.get_data(as_text=True)


def _hrefs(text):
    return [htmllib.unescape(h) for h in re.findall(r'href="([^"]+)"', text)]


def _results(text):
    return text.split('id="results"')[1]


# ---------------------------------------------------------------- categories and rows

@pytest.mark.parametrize("category", list(EXPECTED))
def test_every_category_page_lists_exactly_its_symbols_with_stock_links(db, client, category):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    res, text = _page(client, f"category={category}")
    assert res.status_code == 200 and res.mimetype == "text/html" and BANNER_TEXT in text
    results = _results(text)
    for symbol in EXPECTED[category]:
        assert f'href="/equity/stock/{symbol}"' in results
    others = {r[0] for r in CATEGORY_ROWS} - set(EXPECTED[category])
    for symbol in others:
        assert f'href="/equity/stock/{symbol}"' not in results
    assert f'<b class="current-category">{category} ({len(EXPECTED[category])})</b>' in text


def test_default_category_is_failed_and_all_seven_tabs_show_their_counts(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = _page(client)[1]
    assert 'class="current-category">FAILED (2)' in text
    for name, symbols in EXPECTED.items():
        assert f"{name} ({len(symbols)})" in text


def test_row_shows_status_flags_stored_session_counts_and_marker(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    row = _results(_page(client, "category=INSUFFICIENT_HISTORY")[1]).split("<tbody>")[1]
    assert "CCC" in row and "INSUFFICIENT_HISTORY" in row and "HISTORY_GAPS, PRICE_BREAK_DETECTED" in row
    assert "no previous COMPLETE run to compare" in row


# ---------------------------------------------------------------- counts panel

def test_counts_panel_states_the_rule_and_shows_both_numbers(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    panel = _page(client)[1].split('id="counts"')[1].split('id="categories"')[0]
    assert "rule: recount equals stored run counts" in panel
    assert "Recounted from the run's symbol rows" in panel and "Stored on the run" in panel
    assert re.search(r"<td>VALID</td><td class=\"num\">3</td><td class=\"num\">3</td><td><span class=\"ok\">agree", panel)
    assert "Requested <b>7</b>" in panel and "successful <b>5</b>" in panel and "failed <b>2</b>" in panel
    assert re.search(r'id="balanced"><span class="ok">yes', panel)


def test_a_disagreement_between_recount_and_stored_counts_is_shown(db, client):
    conn = connection.get_connection(db)
    try:
        seed._insert_scan_run(conn, "r-bad", "2026-09-01T09:00:00")
        for symbol, status in (("AAA", "VALID"), ("BBB", "VALID")):
            seed._insert_symbol_result(conn, "r-bad", symbol, symbol, "IT", status, None, {
                "history_gaps": False, "corporate_action_review": False, "price_break_detected": False, "non_eq_series": False})
        seed._complete_run(conn, "r-bad", "2026-09-01T09:30:00", "2026-10-01",
                           {"VALID": 5, "INSUFFICIENT_HISTORY": 0, "STALE": 0, "FAILED": 0},  # really 2 VALID
                           {"history_gaps": 0, "corporate_action_review": 0, "price_break_detected": 0, "non_eq_series": 0},
                           requested=2, successful=1, failed=0)  # 1 + 0 != 2
        conn.commit()
    finally:
        conn.close()
    panel = _page(create_app(demo=False, db_path=db).test_client())[1].split('id="counts"')[1].split('id="categories"')[0]
    assert re.search(r"<td>VALID</td><td class=\"num\">2</td><td class=\"num\">5</td><td><span class=\"bad\">DISAGREE", panel)
    assert re.search(r'id="balanced"><span class="bad">no', panel)


# ---------------------------------------------------------------- banners, notes, empty states

def test_zero_rows_use_the_approved_wording_never_zero_issues(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", []), ("BBB", "VALID", [])])
    text = _page(client, "category=STALE")[1]
    assert 'id="empty-state">no symbols with STALE in run r1 (2 evaluated).' in text
    assert "0 issues" not in text and "<table>" not in _results(text)
    narrowed = _page(client, "category=FAILED&q=zzz")[1]
    assert "no symbols with FAILED match the current filters in run r1 (2 evaluated)" in narrowed


def test_no_complete_run_and_missing_database_are_message_pages_not_errors(db, client, tmp_path, monkeypatch):
    res, text = _page(client)
    assert res.status_code == 200 and "No COMPLETE scan run" in text and BANNER_TEXT in text
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", tmp_path / "never_created.db")
    res, text = _page(create_app(demo=False).test_client())
    assert res.status_code == 200 and "No scans yet" in text and "Traceback" not in text


def test_newer_aborted_run_is_bannered_and_never_shown_as_the_run(db, client):
    _run(db, "r-prev", "2026-09-01T09:00:00", [("AAA", "STALE", [])])
    _run(db, "r-latest", "2026-09-02T09:00:00", [("AAA", "STALE", [])])
    _run(db, "r-aborted", "2026-09-03T09:00:00", [("ZZZ", "STALE", [])], end="ABORTED")
    text = _page(client, "category=STALE")[1]
    assert 'id="newer-run"' in text and "r-aborted" in text and "ABORTED (AUTH_FAILED)" in text
    assert "Run <code>r-latest</code>" in text and "previous COMPLETE full run <code>r-prev</code>" in text
    assert 'href="/equity/stock/ZZZ"' not in text


def test_comparability_notes_and_failed_symbol_note_are_shown(db, client):
    _run(db, "r-prev", "2026-09-01T09:00:00", CATEGORY_ROWS, universe="uv-OLD", review="rv-OLD")
    _run(db, "r-latest", "2026-09-02T09:00:00", CATEGORY_ROWS, universe="uv-NEW", review="rv-NEW")
    text = _page(client, "category=HISTORY_GAPS")[1]
    assert text.count('class="notice comparability"') == 2 and "universe_version differs" in text
    assert 'id="failed-note"' in text and "2 FAILED symbol(s) were not evaluated for HISTORY_GAPS" in text
    assert 'id="failed-note"' not in _page(client, "category=NON_EQ_SERIES")[1]


def test_no_previous_run_says_so_in_the_header(db, client):
    _run(db, "only", "2026-09-01T09:00:00", [("AAA", "STALE", [])])
    text = _page(client, "category=STALE")[1]
    assert 'id="no-previous-run"' in text and "no previous COMPLETE full run to compare with" in text


# ---------------------------------------------------------------- marker rendering

def test_markers_render_for_every_case_and_changed_filter_keeps_only_real_changes(db, client):
    _marker_runs(db)
    results = _results(_page(client, "category=STALE")[1])
    for text in ("status VALID-&gt;STALE", "flag HISTORY_GAPS added", "flag HISTORY_GAPS removed", "new in this run", "unchanged"):
        assert text in results, text
    changed = _results(_page(client, "category=STALE&changed=1")[1])
    assert "status VALID-&gt;STALE" in changed and "new in this run" not in changed
    assert 'name="changed" value="1" checked' in _page(client, "category=STALE&changed=1")[1]


# ---------------------------------------------------------------- URL persistence, sort, pagination

def _query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_every_link_keeps_the_current_filters_in_the_url(db, client):
    _run(db, "r-prev", "2026-09-01T09:00:00", [(f"S{i}", "STALE", [], f"Co {i}", "IT") for i in range(1, 6)])
    _run(db, "r-latest", "2026-09-02T09:00:00", [(f"S{i}", "STALE", [], f"Co {i}", "IT") for i in range(1, 6)])
    q = "category=STALE&q=Co&sector=IT&changed=0&page=2&page_size=2&sort=company_name&dir=desc"
    text = _page(client, q)[1]
    links = _hrefs(text)
    nxt = next(h for h in links if _query(h).get("page") == "3")
    assert _query(nxt) == {"category": "STALE", "q": "Co", "sector": "IT", "page": "3", "page_size": "2",
                           "sort": "company_name", "dir": "desc"}
    prev = next(h for h in links if _query(h).get("page") is None and _query(h).get("page_size") == "2"
                and _query(h).get("sort") == "company_name" and "category=STALE" in h and _query(h).get("q") == "Co")
    assert prev  # page 1 drops the page parameter; everything else is kept
    # a category switch keeps the filters and returns to page 1
    other = next(h for h in links if _query(h).get("category") == "FAILED")
    assert _query(other) == {"category": "FAILED", "q": "Co", "sector": "IT", "page_size": "2",
                             "sort": "company_name", "dir": "desc"}
    # the bookmark link reopens the same view
    bookmark = text.split("Bookmark this view:")[1].split('href="')[1].split('"')[0]
    assert _query(htmllib.unescape(bookmark)) == _query(nxt) | {"page": "2"}  # `nxt` is already unescaped


def test_bookmark_round_trip_reproduces_the_same_rows(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [(f"S{i}", "STALE", [], f"Co {i}", "IT" if i % 2 else "Auto") for i in range(1, 8)])
    first = _page(client, "category=STALE&sector=IT&page=2&page_size=2&sort=symbol&dir=desc")[1]
    bookmark = htmllib.unescape(first.split("Bookmark this view:")[1].split('href="')[1].split('"')[0])
    again = client.get(bookmark).get_data(as_text=True)
    assert re.findall(r'href="/equity/stock/(\w+)"', _results(first)) == re.findall(r'href="/equity/stock/(\w+)"', _results(again))
    assert re.findall(r'href="/equity/stock/(\w+)"', _results(first)) == ["S3", "S1"]


def test_sort_headers_are_limited_to_symbol_company_and_sector(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = _page(client, "category=HISTORY_GAPS")[1]
    head = _results(text).split("<thead>")[1].split("</thead>")[0]
    # the default sort (symbol) is omitted from a URL, so an absent `sort` means symbol
    sorts = [_query(h).get("sort", "symbol") for h in _hrefs(head)]
    assert sorts == ["symbol", "company_name", "sector"]
    assert not any("status" in h or "flag" in h for h in _hrefs(head))
    assert "<th>Status</th>" in head and "<th>Flags</th>" in head  # not links: no status or flag ordering
    assert "dir=desc" in head  # the active column (symbol, ascending) links to the descending order


def test_the_active_sort_column_shows_an_up_or_down_arrow_without_the_safe_filter(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    asc = _results(_page(client, "category=HISTORY_GAPS&sort=company_name&dir=asc")[1]).split("</thead>")[0]
    desc = _results(_page(client, "category=HISTORY_GAPS&sort=company_name&dir=desc")[1]).split("</thead>")[0]
    assert asc.count("&#9650;") == 1 and "&#9660;" not in asc     # up arrow, only on the active column
    assert desc.count("&#9660;") == 1 and "&#9650;" not in desc   # down arrow
    assert "&amp;#9650;" not in asc and "&amp;#9660;" not in desc  # the entity is not double-escaped


def test_pagination_links_exist_only_where_there_is_a_page(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [(f"S{i}", "STALE", []) for i in range(1, 6)])
    first, middle, last = (_page(client, f"category=STALE&page={n}&page_size=2")[1] for n in (1, 2, 3))
    assert 'rel="prev"' not in first and 'rel="next"' in first
    assert 'rel="prev"' in middle and 'rel="next"' in middle
    assert 'rel="prev"' in last and 'rel="next"' not in last


def test_filter_form_is_a_single_get_form_to_this_page(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = _page(client, "category=STALE&sort=sector&dir=desc&page_size=50")[1]
    assert text.lower().count("<form") == 1 and '<form method="get" action="/equity/exceptions">' in text
    form = text.split("<form")[1].split("</form>")[0]
    names = set(re.findall(r'name="(\w+)"', form))
    assert names == {"category", "sort", "dir", "page_size", "q", "sector", "changed"}
    assert "post" not in form.lower()


# ---------------------------------------------------------------- invalid input, methods, escaping

@pytest.mark.parametrize("query", ["category=NOPE", "sort=status", "dir=up", "page=0", "page_size=201", "changed=2", "q=" + "x" * 101])
def test_invalid_parameters_give_a_400_message_page_not_a_stack_trace(db, client, query):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    res, text = _page(client, query)
    assert res.status_code == 400 and "Invalid parameter" in text and BANNER_TEXT in text and "Traceback" not in text


def test_only_get_is_allowed_on_the_page(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)("/equity/exceptions").status_code == 405, method


def test_q_and_sector_are_html_escaped_everywhere_they_are_echoed(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    payload = "<script>alert(1)</script>"
    res, text = _page(client, "category=STALE&q=%3Cscript%3Ealert(1)%3C%2Fscript%3E&sector=%22%3E%3Cimg+src%3Dx%3E")
    assert res.status_code == 200
    assert "<script>alert(1)" not in text and "<img src=x" not in text and '"><img' not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text  # echoed in the form field, escaped
    bad = _page(client, "category=%3Cscript%3Ealert(1)%3C%2Fscript%3E")[1]
    assert "<script>alert(1)" not in bad and "&lt;script&gt;" in bad


def test_percent_and_underscore_in_q_do_not_crash_and_are_escaped(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [("P1", "STALE", [], "50% Foods"), ("P2", "STALE", [], "AB_CD Ltd"),
                                           ("P3", "STALE", [], "ABXCD Ltd")])
    for q, expected in (("%25", ["P1"]), ("_", ["P2"]), ("AB_CD", ["P2"])):
        text = _page(client, f"category=STALE&q={q}")[1]
        assert re.findall(r'href="/equity/stock/(\w+)"', _results(text)) == expected, q
    text = _page(client, "category=STALE&q=%25")[1]
    assert 'value="%"' in text and "q=%25" in text  # the raw % is only ever shown as a field value or percent-encoded
    for nasty in ("%25%25", "__", "%5C", "%27%20OR%201%3D1%20--"):
        assert _page(client, "category=STALE&q=" + nasty)[0].status_code == 200, nasty


# ---------------------------------------------------------------- safety

def test_page_has_no_env_token_score_rank_signal_or_chart_content(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = _page(client, "category=HISTORY_GAPS")[1]
    for forbidden in (".env", "UPSTOX", "access_token", "ACCESS_TOKEN", "api_key", "Bearer"):
        assert forbidden not in text, forbidden
    visible = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", visible).lower()
    assert not re.search(r"\b(score|scores|rank|ranks|ranked|ranking|signal|signals|buy|sell|target|stop-loss|confidence|top picks?)\b",
                         visible.replace("no trading signals", "").replace("scoring blocked", "")), visible
    for tag in ("<script", "<canvas", "<svg", "<img", "<iframe"):
        assert tag not in text.lower(), tag


def test_page_get_does_not_modify_the_database_file(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    for query in ("", "category=STALE&changed=1", "category=HISTORY_GAPS&q=%25&page=3"):
        assert _page(client, query)[0].status_code == 200
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_demo_mode_shows_the_demo_banner(db):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = _page(create_app(demo=True, db_path=db).test_client())[1]
    assert "DEMO DATA - NOT REAL" in text and BANNER_TEXT in text
    assert "DEMO DATA" not in _page(create_app(demo=False, db_path=db).test_client())[1]


def test_page_url_builder_omits_defaults_and_keeps_everything_else():
    base = exceptions.parse_params({})
    assert exceptions.page_url(base) == "/equity/exceptions?category=FAILED"
    full = exceptions.parse_params({"category": "STALE", "q": "a b&c", "sector": "IT", "changed": "1", "page": "3",
                                    "page_size": "50", "sort": "sector", "dir": "desc"})
    url = exceptions.page_url(full)
    assert _query(url) == {"category": "STALE", "q": "a b&c", "sector": "IT", "changed": "1", "page": "3",
                           "page_size": "50", "sort": "sector", "dir": "desc"}
    assert "&c" not in url.split("q=")[1].split("&")[0]  # the ampersand in q is percent-encoded

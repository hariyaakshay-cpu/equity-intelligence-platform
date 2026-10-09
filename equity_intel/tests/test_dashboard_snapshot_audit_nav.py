"""Navigation links to the Snapshot Audit page and the per-symbol drill-down, checked on the seeded demo database
(tmp_path only) and on small tmp_path databases."""
import html
import re
from urllib.parse import quote

import pytest

from dashboard.app import BANNER_TEXT, create_app
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_api import _bars
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run
from equity_intel.tests.test_dashboard_stock_page import client, demo_db  # noqa: F401  (fixtures)

HEADER_LINK = re.compile(r'<a\b[^>]*\bhref="/equity/snapshot-audit"[^>]*\bid="nav-snapshot-audit"[^>]*>Snapshot Audit</a>')
EXCEPTIONS_LINK = re.compile(r'<a\b[^>]*\bhref="/equity/exceptions"[^>]*>Exceptions</a>')


def _get(client, url):
    res = client.get(url)
    return res, res.get_data(as_text=True)


def test_the_main_page_tab_bar_has_a_plain_snapshot_audit_link_after_exceptions(client):
    text = _get(client, "/equity")[1]
    nav = text.split("<nav>")[1].split("</nav>")[0]
    link = re.search(r'<a class="navlink" id="nav-snapshot-audit" href="/equity/snapshot-audit">Snapshot Audit</a>', nav)
    assert link and nav.index('id="nav-exceptions"') < link.start()
    assert re.findall(r'<button data-section="(\w+)"', nav) == [
        "overview", "explorer", "xray", "details", "quality", "audit", "research", "trade"]   # the JS buttons are untouched


@pytest.mark.parametrize("url", [
    "/equity/stock/DEMOAAA", "/equity/stock/NOPE", "/equity/exceptions", "/equity/exceptions?category=NOPE",
    "/equity/snapshot-audit", "/equity/snapshot-audit?view=added", "/equity/snapshot-audit?view=nonsense",
    "/equity/snapshot-audit/symbol/DEMOAAA", "/equity/snapshot-audit/symbol/NOPE", "/equity/snapshot-audit/symbol/DEMOAAA?base=x&other=y",
])
def test_every_stage_1_page_header_links_to_exceptions_and_snapshot_audit(client, url):
    res, text = _get(client, url)
    assert HEADER_LINK.search(text) and EXCEPTIONS_LINK.search(text), url
    assert text.index('id="nav-exceptions"') < text.index('id="nav-snapshot-audit"')
    assert 'href="/equity"' in text and BANNER_TEXT in text and "<script" not in text.lower(), url


def test_the_header_and_tab_bar_links_reach_a_working_snapshot_audit_page(client):
    for url in ("/equity", "/equity/stock/DEMOAAA", "/equity/exceptions", "/equity/snapshot-audit"):
        href = re.search(r'<a [^>]*id="nav-snapshot-audit"[^>]*href="([^"]+)"|<a [^>]*href="([^"]+)"[^>]*id="nav-snapshot-audit"', _get(client, url)[1])
        target = href.group(1) or href.group(2)
        res, text = _get(client, target)
        assert target == "/equity/snapshot-audit" and res.status_code == 200 and 'id="results"' in text, url
        assert "DEMO DATA - NOT REAL" in text


def test_the_stock_detail_card_links_to_the_drill_down_with_the_default_pair_and_keeps_its_other_sentences(client):
    res, text = _get(client, "/equity/stock/DEMOAAA")
    assert res.status_code == 200
    assert "not built yet" not in text and "Phases 3 and 4" not in text
    link = re.search(r'<a href="([^"]+)" id="snapshot-audit-link">([^<]*)</a>\s*<span class="sub">([^<]*)</span>', text)
    assert link and link.group(1) == "/equity/snapshot-audit/symbol/DEMOAAA" and "?" not in link.group(1)   # no base or other
    assert link.group(3) == "(uses the two newest COMPLETE full runs)"
    visible = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())
    assert "This page is read-only; there is no review action." in visible
    assert "Other flags · history gaps:" in visible and "non-EQ series:" in visible
    res, drill = _get(client, link.group(1))
    assert res.status_code == 200 and "Snapshot Audit: DEMOAAA" in drill and "DEMO DATA - NOT REAL" in drill


def test_every_demo_stock_page_link_resolves_to_the_drill_down(client):
    from scripts import dashboard_demo_seed as seed
    for symbol, _name, _sector, status, *_rest in seed.FAKE_SYMBOLS:
        text = _get(client, f"/equity/stock/{symbol}")[1]
        href = re.search(r'<a href="([^"]+)" id="snapshot-audit-link">', text).group(1)
        assert href == f"/equity/snapshot-audit/symbol/{quote(symbol, safe='')}"
        assert client.get(href).status_code == 200, (symbol, status)


def test_a_symbol_absent_from_the_runs_gets_the_clean_404_message_page_and_the_nav_still_works(client):
    res, text = _get(client, "/equity/snapshot-audit/symbol/NOPE")
    assert res.status_code == 404 and "<h1>Symbol not found</h1>" in text and "symbol NOPE is in neither run" in text
    assert "Traceback" not in text and "<table" not in text and HEADER_LINK.search(text)


def test_the_link_href_is_url_quoted_and_the_page_it_points_to_works(db):
    old = [("A&B 50%", "VALID", _bars(), "Odd Co", "IT")]
    new = [("A&B 50%", "VALID", _bars(revised_on=1), "Odd Co", "IT")]
    _make_run(db, "r-old", "2026-09-01T09:00:00", old)
    _make_run(db, "r-new", "2026-09-02T09:00:00", new)
    client = create_app(demo=False, db_path=db).test_client()
    res, text = _get(client, "/equity/stock/" + quote("A&B 50%", safe=""))
    assert res.status_code == 200
    href = re.search(r'<a href="([^"]+)" id="snapshot-audit-link">', text).group(1)
    assert href == "/equity/snapshot-audit/symbol/A%26B%2050%25"                       # quoted, and valid inside the attribute
    assert "A&amp;B 50%" in text                                                         # the visible symbol is escaped
    res, drill = _get(client, href)
    assert res.status_code == 200 and "A&amp;B 50%" in drill and "<table" in drill


def test_the_route_allowlist_is_the_known_list_and_navigation_added_no_route(client):
    rules = sorted(r.rule for r in client.application.url_map.iter_rules() if r.endpoint != "static")
    assert rules == ["/api/equity/candidates", "/api/equity/exceptions", "/api/equity/health", "/api/equity/scan-history",
                     "/api/equity/sectors", "/api/equity/snapshot-audit", "/api/equity/snapshot-audit/symbol/<symbol>",
                     "/api/equity/stock/<symbol>", "/api/equity/summary", "/equity",
                     "/equity/exceptions", "/equity/snapshot-audit", "/equity/snapshot-audit/symbol/<symbol>",
                     "/equity/stock/<symbol>"]
    for rule in rules:
        assert client.post(rule.replace("<symbol>", "DEMOAAA")).status_code in (404, 405), rule


def test_the_navigation_text_has_no_score_rank_signal_or_target_wording(client):
    for url in ("/equity/stock/DEMOAAA", "/equity/snapshot-audit"):
        text = _get(client, url)[1]
        nav_line = re.search(r'<p class="sub"><a href="/equity">.*?</p>', text, re.S).group(0)
        card = re.search(r'<p class="note">Exception view:.*?</p>', text, re.S)
        for chunk in (nav_line, card.group(0) if card else ""):
            visible = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", chunk)).split()).lower()
            assert not re.search(r"\b(score|scores|rank|ranks|ranked|ranking|signal|signals|buy|sell|target|best|worst|top picks?)\b", visible), url


# ---------------------------------------------------------------- fewer than two eligible runs: the drill-down says what the main page says

@pytest.mark.parametrize("n_complete", [0, 1])
def test_drill_down_with_fewer_than_two_eligible_runs_gives_the_same_message_as_the_main_page(db, n_complete):
    if n_complete:
        _make_run(db, "only", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-abort", "2026-09-02T09:00:00", end="ABORTED")
    client = create_app(demo=False, db_path=db).test_client()
    expected = f"a comparison needs two COMPLETE full runs; found {n_complete}"
    main = client.get("/api/equity/snapshot-audit")
    assert main.get_json()["message"] == expected
    res = client.get("/api/equity/snapshot-audit/symbol/AAA")
    assert res.status_code == 200 and res.get_json()["message"] == expected and res.get_json()["comparison_available"] is False
    page = client.get("/equity/snapshot-audit/symbol/AAA")
    assert page.status_code == 200 and f"<p>{expected}</p>" in page.get_data(as_text=True)
    assert f"{expected}." in " ".join(html.unescape(re.sub(r"<[^>]+>", " ", client.get("/equity/snapshot-audit").get_data(as_text=True))).split())

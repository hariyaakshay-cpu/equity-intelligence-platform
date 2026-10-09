"""Navigation links to the Exceptions page, checked end to end on the seeded demo database (tmp_path only)."""
import re

from dashboard.app import BANNER_TEXT
from equity_intel.tests.test_dashboard_stock_page import _page, client, demo_db  # noqa: F401  (fixtures)

LINK = re.compile(r'<a\b[^>]*\bhref="/equity/exceptions"[^>]*>Exceptions</a>')


def _get(client, url):
    res = client.get(url)
    return res, res.get_data(as_text=True)


def test_the_main_page_nav_has_a_real_exceptions_link_not_a_script_button(client):
    text = _get(client, "/equity")[1]
    nav = text.split("<nav>")[1].split("</nav>")[0]
    assert LINK.search(nav) and 'id="nav-exceptions"' in nav
    assert "<button" not in nav.split('id="nav-exceptions"')[1].split("<span")[0]  # the link itself is a plain anchor
    # the JS-driven section buttons are exactly as before (the click handler only binds `nav button`)
    assert re.findall(r'<button data-section="(\w+)"', nav) == [
        "overview", "explorer", "xray", "details", "quality", "audit", "research", "trade"]


def test_the_stage_1_header_links_to_exceptions_on_every_stage_1_page(client):
    for url in ("/equity/stock/DEMOAAA", "/equity/stock/NOPE", "/equity/exceptions", "/equity/exceptions?category=NOPE"):
        res, text = _get(client, url)
        assert LINK.search(text), url
        assert 'href="/equity"' in text and BANNER_TEXT in text, url


def test_following_the_link_from_the_main_page_reaches_a_working_exceptions_page(client):
    href = re.search(r'<a class="navlink" id="nav-exceptions" href="([^"]+)"', _get(client, "/equity")[1]).group(1)
    res, text = _get(client, href)
    assert res.status_code == 200 and 'id="results"' in text and "Exceptions" in text
    assert "DEMO DATA - NOT REAL" in text  # the demo database, never the real one
    # the page's own category links all resolve, including the default category the nav link lands on
    for name in ("FAILED", "STALE", "INSUFFICIENT_HISTORY", "HISTORY_GAPS", "NON_EQ_SERIES", "PRICE_BREAK_DETECTED",
                 "CORPORATE_ACTION_REVIEW"):
        assert _get(client, f"/equity/exceptions?category={name}")[0].status_code == 200, name


def test_exception_rows_link_back_to_stock_detail_and_it_links_forward_again(client):
    text = _get(client, "/equity/exceptions?category=FAILED")[1]
    stock_link = re.search(r'href="(/equity/stock/\w+)"', text.split('id="results"')[1]).group(1)
    res, stock = _get(client, stock_link)
    assert res.status_code == 200 and LINK.search(stock)


def test_nav_additions_add_no_script_no_new_route_and_no_post_target(client):
    stock = _get(client, "/equity/stock/DEMOAAA")[1]
    assert "<script" not in stock.lower()
    for url in ("/equity/exceptions", "/api/equity/exceptions"):
        assert client.post(url).status_code == 405

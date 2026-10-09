"""The server-rendered health panel inside GET /equity (dashboard/templates/health_panel.html).

Every case builds its own tmp_path database and injects the clock through app.config["HEALTH_CLOCK"]. The panel is
built by the same _health_panel closure as /api/equity/health, so the page is compared with that route's JSON.
Reference calendar: Wed 2026-10-07, Thu 10-08, Fri 10-09.
"""
import hashlib
import html
import json
import re
import sqlite3
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest
from markupsafe import escape

from dashboard import app as app_module, health
from dashboard.app import HEALTH_PANEL_UNAVAILABLE, create_app
from equity_intel.persistence import connection, db_path_guard
from equity_intel.persistence.schema import SCHEMA_VERSION
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_freshness_queries import _add_e4_scan
from equity_intel.tests.test_dashboard_health import NOW, _complete, _two_layer_db_with_reasons
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run

PAGE = "/equity"
API = "/api/equity/health"
TEMPLATE = Path(health.__file__).resolve().parent / "templates" / "health_panel.html"
HOSTILE = '<script>alert(1)</script>"\'&<img src=x onerror=alert(2)>'
HOSTILE_ESCAPED = str(escape(HOSTILE))                  # exactly what Jinja's autoescape produces
# every URL the page's own JavaScript fetches (equity.html at the commit before the health panel existed)
KNOWN_FETCH_URLS = {"/api/equity/summary", "/api/equity/sectors?run_id=", "/api/equity/candidates?", "/api/equity/stock/", "/api/equity/scan-history"}


def _client(db_path, now=NOW, demo=False):
    app = create_app(demo=demo, db_path=db_path)
    if now is not None:
        app.config["HEALTH_CLOCK"] = lambda: now
    return app.test_client()


def _get(client, path=PAGE):
    res = client.get(path)
    return res, res.get_data(as_text=True)


def _text(markup):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _panel_html(page):
    start = page.index('<div class="card" id="health-panel">')
    return page[start:page.index('<div id="overview-content">')]


def _row_cells(panel_markup, row_id):
    match = re.search(rf'<tr id="health-row-{row_id}">(.*?)</tr>', panel_markup, re.S)
    assert match, row_id
    return [_text(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", match.group(1), re.S)]


class _Tags(HTMLParser):
    """Every tag name and attribute name the browser would see in a piece of markup."""

    def __init__(self):
        super().__init__()
        self.tags, self.attrs = set(), set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        self.attrs.update(name for name, _ in attrs)


def _populate(db):
    _complete(db, "r1", "2026-10-07T17:00:00", session="2026-10-07", symbols=[("AAA", "VALID", []), ("BBB", "STALE", [])])
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    """The canonical path in tmp_path, not created."""
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    return path


# ---------------------------------------------------------------- where the panel is mounted

def test_the_panel_sits_inside_the_command_center_before_the_javascript_container(db):
    _populate(db)
    _, page = _get(_client(db))
    overview = page[page.index('<section id="overview"'):page.index('<section id="explorer"')]
    assert overview.count('id="health-panel"') == 1 and page.count('id="health-panel"') == 1
    assert overview.index('id="health-panel"') < overview.index('id="overview-content"')
    assert overview.index('id="health-panel"') > overview.index('<section id="overview"')


def test_the_javascript_in_the_page_is_identical_with_and_without_the_panel(db, monkeypatch):
    _populate(db)
    with_panel = _get(_client(db))[1]
    with monkeypatch.context() as patch:                         # a database error while building: the page renders without a panel
        patch.setattr(health, "build", lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("x")))
        without_panel = _get(_client(db))[1]
    script = lambda page: re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    assert 'id="health-panel"' in with_panel and 'id="health-panel"' not in without_panel
    assert script(with_panel) == script(without_panel)


def test_the_page_fetches_exactly_the_urls_it_fetched_before_the_panel(db):
    _populate(db)
    _, page = _get(_client(db))
    urls = re.findall(r"fetch\('([^']*)'", page)
    assert len(urls) == 7 and set(urls) == KNOWN_FETCH_URLS
    assert API not in page


def test_no_javascript_no_inline_handler_no_details_and_no_unsafe_markup_in_the_panel(db):
    _populate(db)
    panel = _panel_html(_get(_client(db))[1])
    for forbidden in ("<script", "<details", "<iframe", "fetch(", "javascript:", "<link", "<img", "<form", "<button", "<input"):
        assert forbidden not in panel.lower(), forbidden
    assert not re.search(r"\son[a-z]+\s*=", panel, re.I)
    source = TEMPLATE.read_text(encoding="utf-8")
    for forbidden in ("|safe", "Markup(", "autoescape", "render_template_string", "<script", "<details"):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------- parity with /api/equity/health

def test_every_row_card_banner_and_list_equals_the_json_route_for_the_same_clock(db):
    _populate(db)
    _make_run(db, "a-full", "2026-10-07T20:00:00", end="ABORTED", abort_reason="INTERRUPTED: KeyboardInterrupt:")
    client = _client(db, datetime(2026, 10, 12, 10, 0, 0))
    body = client.get(API).get_json()
    page = _get(client)[1]
    panel = _panel_html(page)
    text = _text(panel)
    assert body["now_text"] in text and body["expected_session"] in text and body["holiday_caveat"] in text and body["title"] in text
    for row in body["freshness"]:
        cells = _row_cells(panel, row["id"])
        assert row["id"] in cells[0] and row["label"] in cells[0] and (row["layer"] is None or row["layer"] in cells[0])
        assert cells[1] == row["state"]
        assert cells[2].startswith(row["value"]) and all(line in cells[2] for line in row["detail"])
        assert cells[3] == row["rule"]                                                   # the rule text is always visible
        assert cells[4] == (row["now"] or "–")
    banner_texts = [_text(m) for m in re.findall(r'<div class="outdated-banner hp-banner"[^>]*>(.*?)</div>', panel, re.S)]
    assert banner_texts == [b["text"] for b in body["banners"]] and len(banner_texts) == 2
    for layer in body["layers"].values():
        assert layer["denominator_text"] in text and layer["layer"] in text
    assert body["relationship"]["sentence"] in text
    f5 = next(r for r in body["freshness"] if r["id"] == "F5")
    assert [r["run_id"] for r in f5["full"]["runs"]] == ["a-full"] and "a-full" in _text(panel[panel.index('id="health-aborted"'):])


def test_the_printed_now_is_the_injected_clock(db):
    _populate(db)
    for now in (datetime(2026, 10, 8, 9, 30, 0), datetime(2026, 10, 12, 10, 0, 0)):
        assert f"now (IST) {now:%Y-%m-%d %H:%M:%S}" in _text(_panel_html(_get(_client(db, now))[1]))


# ---------------------------------------------------------------- wording: states, calendar, totals, notes

def test_state_badges_print_only_the_three_state_words_and_never_pass_or_a_tick(db):
    _populate(db)
    for now in (datetime(2026, 10, 8, 9, 30, 0), datetime(2026, 10, 12, 10, 0, 0)):
        panel = _panel_html(_get(_client(db, now))[1])
        badges = re.findall(r'<span class="hp-state hp-state-(\w+)">([^<]*)</span>', panel)
        assert len(badges) == 11 and all(cls == word for cls, word in badges) and {w for _, w in badges} <= {"OK", "WARN", "UNKNOWN"}
        words = {w for _, w in badges}
        assert "UNKNOWN" in words and "OK" in words                                          # F8a / F8b are UNKNOWN; F9 and F7 are OK here
        assert ("WARN" in words) == (now.day == 12)                                          # Monday 10-12 is behind the Wednesday session; Thursday 10-08 is not
        lowered = _text(panel).lower()
        assert not re.search(r"\bpass\b|\bpasses\b|\bhealthy\b|\ball clear\b|\bgood\b|\bsafe\b|\bapproved\b|\bverified\b", lowered)
        assert not any(mark in panel for mark in ("\u2713", "\u2714", "\u2705", "&#10003;", "&#10004;", "&check;"))


def test_the_calendar_rows_are_never_ok_even_with_a_verified_looking_calendar(db):
    _complete(db, "r1", "2026-10-07T17:00:00", session="2026-10-07", symbols=[("AAA", "VALID", [])], source="HOLIDAY_FILE", verification="VERIFIED")
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1, calendar="VERIFIED")
    panel = _panel_html(_get(_client(db))[1])
    for row_id in ("F8a", "F8b"):
        assert _row_cells(panel, row_id)[1] == "UNKNOWN"


def test_no_merged_total_the_two_layers_are_separate_cards_with_their_own_denominators(db):
    _complete(db, "r1", "2026-10-07T17:00:00", session="2026-10-07", symbols=[(f"V{i:03d}", "VALID", []) for i in range(120)] + [("W", "STALE", [])])
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"] * 95, features=95)
    panel = _panel_html(_get(_client(db))[1])
    scan_card = _text(re.search(r'id="health-card-scanrun">(.*?)</table>', panel, re.S).group(1))
    e4_card = _text(re.search(r'id="health-card-e4">(.*?)</table>', panel, re.S).group(1))
    assert "121 symbols evaluated by this scan run" in scan_card and "95 symbols with an E4 quality result" in e4_card
    text = _text(panel)
    assert not re.search(r"\b216\b|121 \+ 95", text) and not re.search(r"\b(total|combined|merged|sum)\b", text.lower())
    assert "never added together" in text


def test_the_banner_note_about_the_older_banner_is_always_shown(db):
    _populate(db)
    for now in (datetime(2026, 10, 8, 9, 30, 0), datetime(2026, 10, 12, 10, 0, 0)):          # no banner, then two banners
        panel = _panel_html(_get(_client(db, now))[1])
        assert "older OUTDATED banner" in _text(panel) and "different basis" in _text(panel)
    assert _panel_html(_get(_client(db, datetime(2026, 10, 8, 9, 30, 0)))[1]).count("outdated-banner hp-banner") == 0


def test_the_holiday_caveat_and_the_state_words_follow_the_clock(db):
    _populate(db)
    panel = _panel_html(_get(_client(db, datetime(2026, 10, 12, 10, 0, 0)))[1])
    assert _row_cells(panel, "F1")[1] == "WARN" and health.HOLIDAY_CAVEAT in _text(panel)
    assert "OUTDATED (ScanRun layer)" in _text(panel) and "OUTDATED (E4 layer)" in _text(panel)


def test_the_page_passes_the_same_forbidden_word_scan_as_the_views_test(db):
    _populate(db)
    _make_run(db, "a1", "2026-10-07T20:00:00", end="ABORTED", abort_reason="AUTH_FAILED")
    lowered = _get(_client(db, datetime(2026, 10, 12, 10, 0, 0)))[1].lower()
    for forbidden in ("auc ", "probability", "expected return", "buy", "sell", "log loss", "accuracy"):
        assert forbidden not in lowered, forbidden
    panel = _text(_panel_html(_get(_client(db))[1])).lower()
    for forbidden in ("top pick", "recommend", "target", "stop-loss", "stop loss", "ranking", "ranked", "score:", "best", "worst"):
        assert forbidden not in panel, forbidden


# ---------------------------------------------------------------- escaping

def test_hostile_run_ids_names_symbols_and_values_are_escaped_everywhere(db):
    _complete(db, "r" + HOSTILE, "2026-10-07T17:00:00", session="2026-10-07", symbols=[("S" + HOSTILE, "VALID", [], "Co " + HOSTILE, "IT")])
    _add_e4_scan(db, "e4" + HOSTILE, "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq" + HOSTILE, quality=[], features=0)
    conn = connection.connect(db)
    try:
        conn.execute("INSERT INTO e4_data_quality_results(scan_id,symbol,status,reason,n_bars,w52_complete,break_date,break_ratio,volume_usable) "
                     "VALUES(?,?,?,NULL,252,1,NULL,NULL,1)", ("e4" + HOSTILE, "S" + HOSTILE, "STALE"))
        conn.commit()
    finally:
        conn.close()
    _make_run(db, "a" + HOSTILE, "2026-10-07T20:00:00", end="ABORTED", abort_reason="ZZREASONZZ" + HOSTILE)
    res, page = _get(_client(db))
    assert res.status_code == 200
    panel = _panel_html(page)
    parsed = _Tags()
    parsed.feed(panel)
    assert not parsed.tags & {"script", "img"} and not parsed.attrs & {"onerror", "onclick", "onload"}      # no tag or attribute came from the data
    assert "<script>" not in panel and "<img" not in panel
    assert HOSTILE_ESCAPED in panel                                                        # the ids and names appear, escaped
    assert html.unescape(panel).count("<script>alert(1)</script>") >= 3                      # run, E4 scan and symbol ids all reach the page as text
    assert 'href="/equity/stock/' in panel and "href=\"/equity/stock/S<" not in panel       # the symbol link is percent-quoted
    lists = panel[panel.index('id="health-aborted"'):panel.index('id="health-disagreements"')]
    assert "RECORDED_TEXT_NOT_SHOWN" in lists and "ZZREASONZZ" not in panel                  # the run id is shown (escaped); the recorded abort text is not


def test_hostile_recorded_reasons_never_reach_the_page_only_codes_and_the_notes(db):
    _two_layer_db_with_reasons(db, ["https://x.example/?access_token=SECRET123", "auth failure (401)"],
                               ["acquisition REQUEST_FAILED: ProviderError: Bearer SECRET123", "40 bars; 252 required"])
    _make_run(db, "a1", "2026-10-02T09:00:00", end="ABORTED", abort_reason="INTERRUPTED: KeyboardInterrupt: Bearer SECRET123")
    page = _get(_client(db, datetime(2026, 10, 2, 12, 0, 0)))[1]
    panel = _panel_html(page)
    for secret in ("SECRET123", "Bearer", "https://", "access_token", "ProviderError", "KeyboardInterrupt"):
        assert secret not in panel, secret
    text = _text(panel)
    assert health.REASON_TEXT_NOTE in text and health.ABORT_TEXT_NOTE in text
    assert "RECORDED_TEXT_NOT_SHOWN" in text and "AUTH_FAILURE" in text and "TOO_FEW_BARS" in text and "INTERRUPTED" in text


# ---------------------------------------------------------------- ABORTED runs, demo mode, the read-only page

def test_aborted_runs_never_become_a_layer_card_and_appear_only_in_the_f5_lists(db):
    _populate(db)
    _make_run(db, "x-aborted-full", "2026-10-08T07:00:00", end="ABORTED", abort_reason="CALENDAR_INVALID")
    _make_run(db, "x-aborted-smoke", "2026-10-08T08:00:00", [("AAA", "VALID", [])], end="ABORTED", smoke=json.dumps(["AAA"]), abort_reason="UNEXPECTED_ERROR")
    panel = _panel_html(_get(_client(db))[1])
    cards = panel[panel.index('id="health-layers"'):panel.index('id="health-note-layers"')]
    assert "r1 (FULL)" in _text(cards) and "x-aborted" not in cards
    assert "x-aborted" not in _text(re.search(r'id="health-row-F1">(.*?)</tr>', panel, re.S).group(1))
    lists = panel[panel.index('id="health-aborted"'):panel.index('id="health-disagreements"')]
    assert "x-aborted-full" in lists and "x-aborted-smoke" in lists and "CALENDAR_INVALID" in lists and "UNEXPECTED_ERROR" in lists
    assert "Full runs: 1" in _text(lists) and "smoke runs: 1" in _text(lists)
    assert "x-aborted" not in _text(panel[panel.index('id="health-disagreements"'):])


def test_demo_mode_renders_a_full_panel_with_the_demo_banner(tmp_path, monkeypatch):
    from scripts import dashboard_demo_seed as seed
    canonical, demo = tmp_path / "equity_intel.db", tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", canonical)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    seed.seed_demo_database(demo)
    app = create_app(demo=True)
    app.config["HEALTH_CLOCK"] = lambda: datetime(2026, 9, 26, 12, 0, 0)
    res, page = _get(app.test_client())
    panel = _panel_html(page)
    assert res.status_code == 200 and "DEMO DATA - NOT REAL" in page
    assert "r-demo-latest-complete" in panel and "demo-e4-1" in panel and "DEMO_INDEX" in _text(panel)
    assert [_row_cells(panel, f"F{i}")[1] for i in (1, 2)] == ["OK", "OK"]
    assert len(re.findall(r'<tr id="health-row-', panel)) == 11


def test_requests_leave_the_database_unchanged_and_post_is_still_refused(db):
    _populate(db)
    before = _sha(db)
    client = _client(db)
    for _ in range(3):
        assert client.get(PAGE).status_code == 200
    assert client.post(PAGE).status_code == 405 and client.put(PAGE).status_code == 405
    assert _sha(db) == before


# ---------------------------------------------------------------- a missing or mismatched database, and a database error

def test_a_missing_database_still_shows_the_existing_message_and_no_panel(db_path):
    res, page = _get(_client(db_path))
    assert res.status_code == 200 and "No scans have been recorded yet." in page
    assert 'id="health-panel"' not in page and 'id="overview-content"' in page


def test_a_version_mismatch_still_shows_the_existing_message_and_no_panel(db_path):
    conn = connection.get_connection(db_path)
    try:
        connection.initialize_schema(conn)
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))
        conn.commit()
    finally:
        conn.close()
    res, page = _get(_client(db_path))
    assert res.status_code == 200 and "version mismatch" in page.lower() and str(SCHEMA_VERSION + 1) in page
    assert 'id="health-panel"' not in page


def test_a_database_error_while_building_the_panel_gives_a_fixed_sentence_and_the_page_still_renders(db, monkeypatch):
    _populate(db)

    def broken(conn, now, info=None):
        raise sqlite3.OperationalError("SECRET123 disk I/O error in C:\\Users\\Akshay\\x.db")

    monkeypatch.setattr(health, "build", broken)
    res, page = _get(_client(db))
    assert res.status_code == 200 and HEALTH_PANEL_UNAVAILABLE in page
    assert "SECRET123" not in page and "disk I/O" not in page and "x.db" not in page
    assert 'id="health-panel"' not in page and 'id="overview-content"' in page


def test_any_other_exception_while_building_the_panel_is_not_absorbed(db, monkeypatch):
    _populate(db)

    def broken(conn, now, info=None):
        raise ValueError("a programming error")

    monkeypatch.setattr(health, "build", broken)
    res = _client(db).get(PAGE)
    assert res.status_code == 500 and HEALTH_PANEL_UNAVAILABLE not in res.get_data(as_text=True)


@pytest.mark.parametrize("build_fails", [False, True])
def test_the_connection_is_closed_after_the_page_whether_or_not_the_build_fails(db, monkeypatch, build_fails):
    _populate(db)
    opened = []
    real = app_module._open_checked_connection

    def spy(path):
        conn = real(path)
        opened.append(conn)
        return conn

    def broken(conn, now, info=None):
        raise sqlite3.OperationalError("x")

    monkeypatch.setattr(app_module, "_open_checked_connection", spy)
    if build_fails:
        monkeypatch.setattr(health, "build", broken)
    assert _client(db).get(PAGE).status_code == 200 and len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")                                                       # a closed connection refuses to run SQL

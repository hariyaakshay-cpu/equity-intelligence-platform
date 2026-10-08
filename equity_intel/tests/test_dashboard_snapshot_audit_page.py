"""GET /equity/snapshot-audit: the HTML page built from the same snapshot_audit.build and page_links as the JSON route.

All databases are tmp_path files. The page is read-only, has no JavaScript and no external resources, compares stored
hashes only, and says "bars whose stored hash differs" and nothing about why.
"""
import hashlib
import html
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from dashboard import snapshot_audit, stock_detail, stored_row_integrity
from dashboard.app import create_app
from equity_intel.scanner import snapshots
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_no_unsafe_markup import _files
from equity_intel.tests.test_dashboard_snapshot_audit_api import _bars, _make_versioned_run, _three_runs, _view_runs
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run

PAGE = "/equity/snapshot-audit"
API = "/api/equity/snapshot-audit"


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def _page(client, query=""):
    res = client.get(PAGE + (("?" + query) if query else ""))
    return res, res.get_data(as_text=True)


def _text(markup):
    """Visible text of a page: tags dropped, entities decoded, whitespace collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _hrefs(markup):
    return [html.unescape(h) for h in re.findall(r'href="([^"]*)"', markup)]


def _section(markup, element_id):
    match = re.search(rf'<div class="card" id="{element_id}">(.*?)\n</div>', markup, re.S)
    assert match, element_id
    return match.group(1)


def _table_rows(markup):
    return [[_text(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            for row in re.findall(r"<tr>(.*?)</tr>", markup, re.S)]


# ---------------------------------------------------------------- default, explicit and swapped pairs

def test_default_page_shows_the_two_newest_runs_the_counts_and_the_fixed_sentences(db, client):
    _three_runs(db)
    res, page = _page(client)
    assert res.status_code == 200 and "<h1>Snapshot Audit</h1>" in page
    details = _table_rows(_section(page, "run-selection"))
    assert ["Run", "r2", "r3"] in details and ["Started", "2026-09-02T09:00:00", "2026-09-03T09:00:00"] in details
    body = client.get(API).get_json()
    visible = _text(page)
    for line in body["counts_text"].values():
        assert line in visible
    assert "This page compares stored hashes; it does not recompute them." in visible
    assert body["metric"]["note"] in visible and "possible vendor revision" in visible and "NOT_DEFINED" in visible
    assert body["one_sided_note"] in visible
    assert 'id="swap-note"' not in page and 'id="older-pair-note"' not in page and 'id="newer-run"' not in page


def test_explicit_pair_is_used_and_marked_as_not_the_latest_pair(db, client):
    _three_runs(db)
    res, page = _page(client, "base=r1&other=r2")
    assert res.status_code == 200
    assert ["Run", "r1", "r2"] in _table_rows(_section(page, "run-selection"))
    note = _text(re.search(r'<p class="notice" id="older-pair-note">.*?</p>', page, re.S).group(0))
    assert "not the latest pair" in note and "r2 and r3" in note


def test_the_older_pair_note_appears_only_when_the_pair_is_not_the_latest(db, client):
    _three_runs(db)
    assert 'id="older-pair-note"' not in _page(client)[1]
    assert 'id="older-pair-note"' not in _page(client, "base=r2&other=r3")[1]
    assert 'id="older-pair-note"' in _page(client, "base=r1&other=r3")[1]
    assert 'id="older-pair-note"' in _page(client, "base=r1&other=r2")[1]
    assert 'id="older-pair-note"' not in _page(client, "base=r3&other=r2")[1]   # swapped, but it is the latest pair


def test_reversed_base_and_other_are_swapped_with_the_visible_note(db, client):
    _three_runs(db)
    res, page = _page(client, "base=r3&other=r1")
    assert res.status_code == 200
    note = _text(re.search(r'<p class="notice" id="swap-note">.*?</p>', page, re.S).group(0))
    assert "base (r3) is newer than other (r1)" in note and "older run r1 is used as base" in note
    assert ["Run", "r1", "r3"] in _table_rows(_section(page, "run-selection"))
    assert _page(client, "base=r1&other=r3")[1].count("<tr>") == page.count("<tr>")


def test_run_details_and_every_comparability_note_in_one_list_with_the_fixed_note_last(db, client):
    _make_versioned_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())], universe="uv-OLD", review="rv-OLD", git="git-OLD")
    _make_versioned_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars(revised_on=2))], universe="uv-NEW", review="rv-NEW", git="git-NEW")
    page = _page(client)[1]
    details = _table_rows(_section(page, "run-selection"))
    assert ["Universe version", "uv-OLD", "uv-NEW"] in details and ["Scanner git commit", "git-OLD", "git-NEW"] in details
    assert ["Corporate-action review version", "rv-OLD", "rv-NEW"] in details
    items = [_text(i) for i in re.findall(r"<li>(.*?)</li>", re.search(r'<ul id="comparability-notes">(.*?)</ul>', page, re.S).group(1), re.S)]
    assert items == client.get(API).get_json()["comparability_notes"] and len(items) == 4
    assert items[-1] == snapshot_audit.NO_HASH_VERSION_NOTE


def test_a_missing_run_value_is_shown_as_not_recorded(db, client):
    _make_versioned_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())], universe="u", review="r", git="g")
    _make_versioned_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars())], universe="u", review="r", git="")
    details = _table_rows(_section(_page(client)[1], "run-selection"))
    assert ["Scanner git commit", "g", "not recorded"] in details


# ---------------------------------------------------------------- the three views

def test_revised_view_table_has_the_listed_columns_and_matches_the_json_rows(db, client):
    _view_runs(db)
    res, page = _page(client)
    rows = _table_rows(_section(page, "results"))
    assert rows[0] == ["Symbol ▲", "Company", "Sector", "Overlapping bars", "bars whose stored hash differs",
                       "First differing date", "Last differing date"]
    api_rows = client.get(API).get_json()["rows"]
    assert [r[0] for r in rows[1:]] == [r["symbol"] for r in api_rows] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    assert rows[1] == ["R1", "Alpha 50% Co", "IT", "5", "1", api_rows[0]["first_differing_date"], api_rows[0]["last_differing_date"]]
    assert rows[5][2] == "not recorded"            # R5 has no stored sector
    assert "/equity/stock/R1" in _hrefs(page)


def test_added_and_removed_views_have_status_columns_and_the_right_symbols(db, client):
    _view_runs(db)
    added = _table_rows(_section(_page(client, "view=added")[1], "results"))
    assert added[0] == ["Symbol ▲", "Company", "Sector", "Status"]
    assert sorted(r[0] for r in added[1:]) == ["NEW1", "NEW2"] and all(r[3] == "VALID" for r in added[1:])
    removed = _table_rows(_section(_page(client, "view=removed")[1], "results"))
    assert [r[0] for r in removed[1:]] == ["GONE"]


def test_view_tabs_show_counts_and_mark_the_current_view(db, client):
    _view_runs(db)
    page = _page(client, "view=added")[1]
    tabs = _text(_section(page, "views"))
    assert "Symbols with bars whose stored hash differs (7)" in tabs and "Added symbols (2)" in tabs and "Removed symbols (1)" in tabs
    assert re.search(r'<b class="current-view">Added symbols \(2\)</b>', page)
    hrefs = _hrefs(_section(page, "views"))
    assert len(hrefs) == 2 and all("base=r-old" in h and "other=r-new" in h for h in hrefs)


def test_sort_headers_are_limited_to_symbol_company_and_sector_with_plain_text_arrows(db, client):
    _view_runs(db)
    page = _page(client, "sort=sector&dir=desc")[1]
    header = re.search(r"<thead>.*?</thead>", _section(page, "results"), re.S).group(0)
    assert len(re.findall(r"<a ", header)) == 3
    assert "&#9660;" in header and "&#9650;" not in header
    assert "sort=differing" not in page and "sort=overlapping" not in page and "sort=status" not in page
    assert "&#9650;" in re.search(r"<thead>.*?</thead>", _section(_page(client)[1], "results"), re.S).group(0)


def test_filters_pagination_and_clear_filters_links(db, client):
    _view_runs(db)
    page = _page(client, "page_size=3&q=Ltd&sector=Auto")[1]
    text = _text(_section(page, "results"))
    assert "page 1 of 1" in text or "page 1 of 2" in text
    assert "clear filters" in _text(_section(page, "filters"))
    clear = [h for h in _hrefs(_section(page, "filters")) if "q=" not in h and "sector=" not in h]
    assert clear and "page_size=3" in clear[0] and "base=r-old" in clear[0]
    page_one = _page(client, "page_size=3")[1]
    assert 'rel="next"' in page_one and 'rel="prev"' not in page_one
    assert 'rel="prev"' in _page(client, "page_size=3&page=3")[1] and 'rel="next"' not in _page(client, "page_size=3&page=3")[1]


def test_percent_and_underscore_in_q_are_literal_on_the_page(db, client):
    _view_runs(db)
    assert [r[0] for r in _table_rows(_section(_page(client, "q=%25")[1], "results"))[1:]] == ["R1"]
    assert [r[0] for r in _table_rows(_section(_page(client, "q=B_C")[1], "results"))[1:]] == ["R2"]
    assert [r[0] for r in _table_rows(_section(_page(client, "view=added&q=%25")[1], "results"))[1:]] == ["NEW2"]


def test_empty_state_states_the_denominators(db, client):
    _view_runs(db)
    page = _page(client, "q=no-such-symbol")[1]
    notice = _text(re.search(r'<p id="empty-state">.*?</p>', page, re.S).group(0))
    assert notice == client.get(API + "?q=no-such-symbol").get_json()["notice"] + "."
    assert "overlapping bars" in notice or "symbols in the newer run" in notice
    _make_run(db, "r-same-a", "2026-09-10T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-same-b", "2026-09-11T09:00:00", [("AAA", "VALID", _bars())])
    quiet = _text(re.search(r'<p id="empty-state">.*?</p>', _page(client)[1], re.S).group(0))
    assert quiet.startswith("no comparable symbol has bars whose stored hash differs (5 overlapping bars were compared across 1 comparable symbols")
    assert "<table" not in _section(_page(client)[1], "results")


# ---------------------------------------------------------------- run selection form

def test_run_selection_form_is_a_plain_get_form_that_preserves_view_state_and_resets_the_page(db, client):
    _view_runs(db)
    page = _page(client, "view=added&q=New&sector=IT&sort=company_name&dir=desc&page_size=10&page=2")[1]
    form = re.search(r'<form method="get" action="/equity/snapshot-audit">(.*?)</form>', _section(page, "run-selection"), re.S).group(1)
    hidden = dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)">', form))
    assert hidden == {"view": "added", "q": "New", "sector": "IT", "sort": "company_name", "dir": "desc", "page_size": "10"}
    assert 'name="page"' not in form and "<select name=\"base\">" in form and "<select name=\"other\">" in form
    assert '<option value="r-old" selected>' in re.search(r'<select name="base">.*?</select>', form, re.S).group(0)
    assert '<option value="r-new" selected>' in re.search(r'<select name="other">.*?</select>', form, re.S).group(0)
    plain = re.search(r'<form method="get" action="/equity/snapshot-audit">(.*?)</form>', _section(_page(client)[1], "run-selection"), re.S).group(1)
    assert 'type="hidden"' not in plain          # defaults are not repeated


def test_the_selects_list_the_newest_fifty_eligible_runs_and_always_include_the_chosen_pair(db, client):
    for i in range(53):
        _make_run(db, f"r{i:02d}", f"2026-07-{i // 24 + 1:02d}T{i % 24:02d}:00:00", [("AAA", "VALID", _bars())])
    page = _page(client)[1]
    base_select = re.search(r'<select name="base">.*?</select>', page, re.S).group(0)
    assert base_select.count("<option") == 50 and "3 older not listed" in _text(page)
    old = _page(client, "base=r00&other=r01")[1]
    old_select = re.search(r'<select name="base">.*?</select>', old, re.S).group(0)
    assert old_select.count("<option") == 51 and '<option value="r00" selected>' in old_select


def test_submitting_the_form_values_round_trips_to_the_same_pair(db, client):
    _three_runs(db)
    page = _page(client, "base=r1&other=r3")[1]
    base = re.search(r'<option value="([^"]+)" selected>', re.search(r'<select name="base">.*?</select>', page, re.S).group(0)).group(1)
    other = re.search(r'<option value="([^"]+)" selected>', re.search(r'<select name="other">.*?</select>', page, re.S).group(0)).group(1)
    assert (base, other) == ("r1", "r3")
    assert ["Run", "r1", "r3"] in _table_rows(_section(_page(client, f"base={base}&other={other}")[1], "run-selection"))


# ---------------------------------------------------------------- runs not used, banner, no comparison

def test_runs_not_used_table_lists_reasons_counts_not_recorded_and_the_remainder(db, client):
    _three_runs(db)
    _make_run(db, "r-smoke", "2026-09-05T09:00:00", [("AAA", "VALID", []), ("BBB", "VALID", [])], smoke=json.dumps(["AAA", "BBB"]))
    for i in range(22):
        _make_run(db, f"r-abort-{i:02d}", f"2026-08-{i + 1:02d}T09:00:00", end="ABORTED")
    _make_run(db, "r-running", "2026-09-06T09:00:00", end="RUNNING")
    page = _page(client)[1]
    rows = _table_rows(_section(page, "ineligible-runs"))
    assert rows[0] == ["Run", "Started", "Reason", "Symbols requested", "Symbols stored"]
    assert len(rows) - 1 == 20
    assert rows[1][:3] == ["r-running", "2026-09-06T09:00:00", "RUNNING (not finished)"] and rows[1][3] == "not recorded"
    assert rows[2][0] == "r-smoke" and rows[2][2] == "smoke run (--symbols, 2 symbols)" and rows[2][4] == "2"
    assert "and 4 older run(s) not listed." in _text(page)
    assert any(r[2] == "ABORTED (AUTH_FAILED)" for r in rows[1:])


def test_no_ineligible_runs_says_so(db, client):
    _three_runs(db)
    assert "No ABORTED, RUNNING or smoke runs exist." in _text(_page(client)[1])


def test_a_newer_aborted_run_is_bannered_and_not_used(db, client):
    _three_runs(db)
    _make_run(db, "r-abort", "2026-09-09T09:00:00", [("AAA", "VALID", _bars(revised_on=1))], end="ABORTED")
    page = _page(client)[1]
    banner = _text(re.search(r'<p class="notice" id="newer-run">.*?</p>', page, re.S).group(0))
    assert "r-abort" in banner and "ABORTED" in banner and "not used for this comparison" in banner
    assert ["Run", "r2", "r3"] in _table_rows(_section(page, "run-selection"))


@pytest.mark.parametrize("n_complete", [0, 1])
def test_fewer_than_two_eligible_runs_gives_the_explicit_message_and_no_tables_of_changes(db, client, n_complete):
    if n_complete:
        _make_run(db, "only", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-abort", "2026-09-02T09:00:00", end="ABORTED")
    res, page = _page(client)
    assert res.status_code == 200
    assert f"a comparison needs two COMPLETE full runs; found {n_complete}." in _text(_section(page, "run-selection"))
    for absent in ('id="counts"', 'id="views"', 'id="results"', 'id="filters"', "<select", 'id="run-details"'):
        assert absent not in page, absent
    assert "r-abort" in _text(_section(page, "ineligible-runs"))
    assert "no changes" not in _text(page).lower() and "0 revisions" not in _text(page).lower()
    if n_complete:
        assert "only" in _text(_section(page, "run-selection"))


def test_an_empty_database_with_no_runs_is_the_same_explicit_message(db, client):
    res, page = _page(client)
    assert res.status_code == 200 and "a comparison needs two COMPLETE full runs; found 0." in _text(page)


def test_a_missing_database_is_a_message_page_not_an_error(tmp_path, monkeypatch):
    from equity_intel.persistence import db_path_guard
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", tmp_path / "absent.db")
    missing = create_app(demo=False, db_path=tmp_path / "absent.db").test_client().get(PAGE)
    assert missing.status_code == 200 and "No scans yet" in missing.get_data(as_text=True)
    assert "<table" not in missing.get_data(as_text=True)


# ---------------------------------------------------------------- invalid parameters, methods, escaping

@pytest.mark.parametrize("query", [
    "view=both", "view=REVISED", "sort=differing_bars", "sort=status", "sort=overlapping_bars", "sort=;DROP", "dir=up",
    "dir=ASC", "page=0", "page=-1", "page=abc", "page=1.5", "page_size=0", "page_size=201", "page_size=x",
    "q=" + "x" * 101, "sector=" + "y" * 101, "base=" + "z" * 101 + "&other=r1", "base=r1", "other=r3",
    "base=r1&other=r1", "base=nope&other=r1", "base=r1&other=nope",
])
def test_each_invalid_parameter_gives_a_400_message_page(db, client, query):
    _three_runs(db)
    res, page = _page(client, query)
    assert res.status_code == 400 and res.mimetype == "text/html"
    assert "<h1>Invalid parameter</h1>" in page and "Traceback" not in page and "<table" not in page
    assert _text(page).count(client.get(f"{API}?{query}").get_json()["error"]) == 1   # the same words as the JSON route


@pytest.mark.parametrize("kind, label", [("ABORTED", "ABORTED"), ("RUNNING", "RUNNING"), ("SMOKE", "smoke run, --symbols")])
@pytest.mark.parametrize("which", ["base", "other"])
def test_aborted_running_and_smoke_runs_as_base_or_other_give_the_400_message(db, client, kind, label, which):
    _three_runs(db)
    if kind == "SMOKE":
        _make_run(db, "r-bad", "2026-09-05T09:00:00", [("AAA", "VALID", [])], smoke=json.dumps(["AAA"]))
    else:
        _make_run(db, "r-bad", "2026-09-05T09:00:00", end=kind)
    query = "base=r-bad&other=r3" if which == "base" else "base=r1&other=r-bad"
    res, page = _page(client, query)
    assert res.status_code == 400
    assert f"run r-bad is not a COMPLETE full run ({label})" in _text(page)


def test_post_put_delete_and_patch_are_405(db, client):
    _three_runs(db)
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)(PAGE).status_code == 405, method


def test_script_text_in_base_is_escaped_in_the_400_page(db, client):
    _three_runs(db)
    res, page = _page(client, "base=%3Cscript%3Ex%3C%2Fscript%3E&other=r3")
    assert res.status_code == 400
    assert "<script>x</script>" not in page and "&lt;script&gt;x&lt;/script&gt;" in page
    assert "<script" not in page


def test_script_text_in_q_sector_and_the_form_fields_is_escaped_on_the_normal_page(db, client):
    _view_runs(db)
    payload = "%22%3E%3Cscript%3Ealert(1)%3C%2Fscript%3E"
    for query in (f"q={payload}", f"sector={payload}", f"view=added&q={payload}", f"q={payload}&sector={payload}"):
        res, page = _page(client, query)
        assert res.status_code == 200, query
        assert "<script" not in page and '"><script' not in page, query
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page or "&lt;script&gt;" in page, query
        for href in _hrefs(page):
            assert "<" not in href and ">" not in href and '"' not in href
    odd = _page(client, "q=%25_%27")[1]
    assert "value=\"%_&#39;\"" in odd


def test_company_and_sector_text_from_the_database_is_escaped(db, client):
    old = [("AAA", "VALID", _bars(), "<b>Bold</b> & Co", "<i>IT</i>")]
    new = [("AAA", "VALID", _bars(revised_on=1), "<b>Bold</b> & Co", "<i>IT</i>")]
    _make_run(db, "r-old", "2026-09-01T09:00:00", old)
    _make_run(db, "r-new", "2026-09-02T09:00:00", new)
    page = _page(client)[1]
    assert "<b>Bold</b>" not in page and "&lt;b&gt;Bold&lt;/b&gt; &amp; Co" in page and "<i>IT</i>" not in page


# ---------------------------------------------------------------- links

def test_links_keep_the_resolved_run_ids_and_every_followed_link_works(db, client):
    _view_runs(db)
    page = _page(client, "page_size=3&sort=company_name&dir=desc")[1]
    own = [h for h in _hrefs(page) if h.startswith(PAGE)]
    assert own
    for href in own:
        query = parse_qs(urlsplit(href).query)
        assert query["base"] == ["r-old"] and query["other"] == ["r-new"], href
        assert client.get(href).status_code == 200, href
    default_page = _page(client)[1]
    assert all("base=r-old&other=r-new" in h for h in _hrefs(default_page) if h.startswith(PAGE + "?"))
    # a later run does not move a bookmark taken from the default page
    bookmark = [h for h in _hrefs(default_page) if h.startswith(PAGE)][0]
    _make_run(db, "r-later", "2026-09-20T09:00:00", [("R1", "VALID", _bars(revised_on=3))])
    assert ["Run", "r-old", "r-new"] in _table_rows(_section(client.get(bookmark).get_data(as_text=True), "run-selection"))


def test_the_page_and_the_json_route_show_the_same_rows_for_every_view_and_pair(db, client):
    _view_runs(db)
    for query in ("", "view=added", "view=removed", "base=r-new&other=r-old", "sector=UNKNOWN", "sort=sector&dir=desc&page_size=2&page=2"):
        symbols = [r[0] for r in _table_rows(_section(_page(client, query)[1], "results"))[1:]]
        assert symbols == [r["symbol"] for r in client.get(f"{API}?{query}").get_json()["rows"]], query


def test_there_is_no_drill_down_link_yet(db, client):
    _view_runs(db)
    for query in ("", "view=added", "view=removed"):
        for href in _hrefs(_page(client, query)[1]):
            assert not href.startswith(PAGE + "/"), href


# ---------------------------------------------------------------- hashing, read-only, resources, wording

def test_the_page_never_calls_a_hash_function(db, client, monkeypatch):
    _view_runs(db)
    _make_run(db, "r-late", "2026-09-03T09:00:00", [("R1", "VALID", _bars(revised_on=3))])
    calls = []

    def spy(module, name):
        original = getattr(module, name)
        monkeypatch.setattr(module, name, lambda *a, **k: calls.append(name) or original(*a, **k))

    spy(snapshots, "compute_content_hash_from_stored_row")
    spy(snapshots, "compute_content_hash")
    spy(stock_detail, "compute_content_hash_from_stored_row")
    spy(stored_row_integrity, "compute_content_hash_from_stored_row")
    spy(stored_row_integrity, "check_rows")
    for query in ("", "view=added", "view=removed", "base=r-old&other=r-new", "base=r-new&other=r-old",
                  "base=r-old&other=r-late&q=R", "sort=sector&dir=desc&page=2&page_size=2", "view=bad", "base=x&other=y"):
        client.get(f"{PAGE}?{query}")
    assert calls == []


def test_requests_never_modify_the_database_file(db, client):
    _view_runs(db)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    for query in ("", "view=added", "view=removed", "base=r-new&other=r-old", "q=%25&sort=sector", "sort=bad", "base=r-old",
                  "base=nope&other=r-new", "page=9&page_size=2"):
        client.get(f"{PAGE}?{query}")
    client.post(PAGE)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_the_page_has_no_javascript_no_external_resources_and_no_chart(db, client):
    _view_runs(db)
    for query in ("", "view=added", "view=removed"):
        page = _page(client, query)[1]
        assert "<script" not in page.lower() and " onclick" not in page.lower() and "javascript:" not in page.lower()
        assert "<canvas" not in page and "<svg" not in page and "<img" not in page and "<iframe" not in page
        assert not re.findall(r'(?:src|href)="(?:https?:)?//', page)
        assert "<link" not in page and "@import" not in page and "url(" not in page


def test_the_template_is_covered_by_the_no_safe_no_markup_scan(db, client):
    template = next(p for p in _files("*.html") if p.name == "snapshot_audit.html")
    source = template.read_text(encoding="utf-8")
    assert not re.search(r"\|\s*safe\b", source) and not re.search(r"autoescape\s+(false|off)", source, re.I)
    assert "﻿" not in source and "\r" not in source


def test_no_env_token_score_rank_signal_or_target_wording_on_any_view(db, client):
    _view_runs(db)
    _make_run(db, "r-abort", "2026-09-09T09:00:00", end="ABORTED")
    for query in ("", "view=added", "view=removed", "q=zzz", "base=r-new&other=r-old"):
        page = _page(client, query)[1]
        for forbidden in (".env", "UPSTOX", "access_token", "ACCESS_TOKEN", "api_key", "Bearer"):
            assert forbidden not in page, forbidden
        visible = _text(page.split("<main>", 1)[1]).lower()   # this page's own content; the shared stage banner above <main> is not ours
        assert not re.search(r"\b(score|scores|scored|rank|ranks|ranked|ranking|signal|signals|buy|sell|target|targets|"
                             r"stop-?loss|confidence|top picks?|best|worst|strongest|weakest)\b", visible), query
        assert "possible vendor revision" in visible and "does not classify the cause" in visible

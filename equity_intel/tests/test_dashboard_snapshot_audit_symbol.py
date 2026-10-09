"""The per-symbol drill-down: GET /equity/snapshot-audit/symbol/<symbol> and /api/equity/snapshot-audit/symbol/<symbol>.

All databases are tmp_path files. This is the only Phase 3 view that recomputes a hash, and only through
stored_row_integrity.check_rows over the viewed symbol's own stored bars in the two runs. The main page and the
main JSON route still recompute nothing.
"""
import hashlib
import html
import json
import re
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from dashboard import queries, snapshot_audit, stock_detail, stored_row_integrity
from dashboard.app import create_app
from equity_intel.persistence import connection
from equity_intel.scanner import snapshots
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_api import _bars, _make_versioned_run, _three_runs
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _d, _make_run
from equity_intel.tests.test_dashboard_snapshot_audit_queries import demo_db  # noqa: F401  (fixture)
from scripts import dashboard_demo_seed as seed

PAGE = "/equity/snapshot-audit/symbol/"
API = "/api/equity/snapshot-audit/symbol/"
MAIN_API = "/api/equity/snapshot-audit"
MAIN_PAGE = "/equity/snapshot-audit"


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def _text(markup):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _hrefs(markup):
    return [html.unescape(h) for h in re.findall(r'href="([^"]*)"', markup)]


def _section(markup, element_id):
    match = re.search(rf'<div class="card" id="{element_id}">(.*?)\n</div>', markup, re.S)
    assert match, element_id
    return match.group(1)


def _page(client, symbol, query=""):
    res = client.get(PAGE + quote(symbol, safe="") + (("?" + query) if query else ""))
    return res, res.get_data(as_text=True)


def _api(client, symbol, query=""):
    res = client.get(API + quote(symbol, safe="") + (("?" + query) if query else ""))
    return res, res.get_json()


def _two_runs(db, old_bars, new_bars, *, name="Alpha Co", sector="IT"):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", old_bars, name, sector)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", new_bars, name, sector)])


def _with_stored_hash(monkeypatch, db, run_id, started_at, symbols, hashes):
    """Create a COMPLETE run in which the stored hash of the given dates is `hashes[date]` instead of the real one."""
    original = snapshots.compute_content_hash
    with monkeypatch.context() as patch:
        patch.setattr(snapshots, "compute_content_hash", lambda day, *a, **k: hashes.get(day) or original(day, *a, **k))
        _make_run(db, run_id, started_at, symbols)


def _stored(db, run_id, symbol):
    conn = connection.get_read_only_connection(db)
    try:
        return [dict(zip(("trading_date", "open", "high", "low", "close", "volume"), r)) for r in conn.execute(
            "SELECT trading_date, open, high, low, close, volume FROM price_fetch_snapshots WHERE scan_run_id = ? AND symbol = ? "
            "ORDER BY trading_date", (run_id, symbol))]
    finally:
        conn.close()


# ---------------------------------------------------------------- content for a comparable symbol

def test_comparable_symbol_shows_names_statuses_counts_and_the_differing_bars_newest_first(db, client):
    _two_runs(db, _bars(), [(_d(i), 100.0 + i + (0.5 if i in (1, 3) else 0.0)) for i in range(5)])
    res, body = _api(client, "AAA")
    assert res.status_code == 200 and body["state"] == "comparable"
    assert (body["symbol"], body["company_name"], body["sector"]) == ("AAA", "Alpha Co", "IT")
    assert body["base_symbol"] == {"present": True, "status": "VALID", "status_reason": None, "stored_bars": 5}
    assert body["other_symbol"]["status"] == "VALID" and body["other_symbol"]["stored_bars"] == 5
    assert body["counts"] == {"overlapping_bars": 5, "differing_bars": 2, "only_in_older": 0, "only_in_newer": 0}
    assert body["counts_text"]["differing"] == "2 of 5 overlapping bars differ (bars whose stored hash differs)"
    assert [r["trading_date"] for r in body["rows"]] == [_d(3), _d(1)]               # newest date first
    assert body["truncated"] is False and body["truncation_notice"] is None and body["cap"] == 300
    assert body["scoring_status"] == "BLOCKED_B2" and body["layer"] == "ScanRun"


def test_side_by_side_values_are_the_stored_rows_of_each_run_and_differing_fields_are_listed(db, client):
    _two_runs(db, _bars(), [(_d(i), 100.0 + i + (0.5 if i == 2 else 0.0), 1000 + (7 if i == 2 else 0)) for i in range(5)])
    body = _api(client, "AAA")[1]
    (row,) = body["rows"]
    old = next(r for r in _stored(db, "r-old", "AAA") if r["trading_date"] == _d(2))
    new = next(r for r in _stored(db, "r-new", "AAA") if r["trading_date"] == _d(2))
    assert row["base"] == {k: old[k] for k in ("open", "high", "low", "close", "volume")}
    assert row["other"] == {k: new[k] for k in ("open", "high", "low", "close", "volume")}
    assert row["differing_fields"] == ["open", "high", "low", "close", "volume"] and row["note"] is None
    _, page = _page(client, "AAA")
    table = re.search(r'<table id="differing-bars">(.*?)</table>', page, re.S).group(1)
    body_row = re.findall(r"<tr>(.*?)</tr>", table, re.S)[-1]
    cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", body_row, re.S)]
    assert cells[:2] == [_d(2), "upstox"]
    assert cells[2:12] == [old["open"], new["open"], old["high"], new["high"], old["low"], new["low"], old["close"], new["close"],
                           str(old["volume"]), str(new["volume"])]
    assert cells[12] == "open, high, low, close, volume"


def test_a_volume_only_difference_lists_only_volume(db, client):
    _two_runs(db, [(_d(0), 100.0, 1000)], [(_d(0), 100.0, 1500)])
    assert _api(client, "AAA")[1]["rows"][0]["differing_fields"] == ["volume"]


def test_equal_displayed_values_with_a_different_stored_hash_say_so_and_do_not_explain(db, client, monkeypatch):
    _with_stored_hash(monkeypatch, db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())], {_d(1): "f" * 64})
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars())])
    body = _api(client, "AAA")[1]
    (row,) = body["rows"]
    assert row["differing_fields"] == [] and row["base"] == row["other"]
    assert row["note"] == "stored hash differs although the displayed values are equal; this page does not explain why"
    page = _page(client, "AAA")[1]
    assert "stored hash differs although the displayed values are equal; this page does not explain why" in _text(page)


def test_comparable_with_zero_differing_bars_states_the_denominator(db, client):
    _two_runs(db, _bars(), _bars())
    body = _api(client, "AAA")[1]
    assert body["state"] == "comparable" and body["rows"] == []
    assert body["counts_text"]["differing"] == "0 of 5 overlapping bars differ (bars whose stored hash differs)"
    page = _page(client, "AAA")[1]
    assert "0 of 5 overlapping bars differ (bars whose stored hash differs)." in _text(_section(page, "results"))
    assert 'id="differing-bars"' not in page


def test_one_sided_bars_are_counted_separately_and_never_listed_as_differing(db, client):
    _two_runs(db, _bars(n=5), [(_d(i), 100.0 + i) for i in range(2, 8)])
    body = _api(client, "AAA")[1]
    assert body["counts"] == {"overlapping_bars": 3, "differing_bars": 0, "only_in_older": 2, "only_in_newer": 3}
    assert body["counts_text"]["one_sided"] == "2 bars are only in the older run and 3 are only in the newer run"


def test_runs_sharing_no_bar_say_zero_of_zero(db, client):
    _two_runs(db, [(_d(i), 100.0) for i in range(3)], [(_d(i), 100.0) for i in range(10, 13)])
    body = _api(client, "AAA")[1]
    assert body["counts_text"]["differing"].startswith("0 of 0 overlapping bars differ") and body["no_overlap_note"]
    assert "share no bar" in _text(_page(client, "AAA")[1])


# ---------------------------------------------------------------- the cap at 300

def _differing_bars(db, n):
    _two_runs(db, [(_d(i), 100.0 + i) for i in range(n)], [(_d(i), 100.5 + i) for i in range(n)])


@pytest.mark.parametrize("n, truncated", [(299, False), (300, False), (301, True)])
def test_the_cap_boundary_at_299_300_and_301_differing_bars(db, client, n, truncated):
    _differing_bars(db, n)
    body = _api(client, "AAA")[1]
    assert body["counts"]["differing_bars"] == n and len(body["rows"]) == min(n, 300) and body["truncated"] is truncated
    page = _page(client, "AAA")[1]
    if truncated:
        assert body["truncation_notice"] == "truncated at 300 of 301 differing bars: the 300 newest are shown"
        assert "truncated at 300 of 301" in _text(page)
        assert body["rows"][0]["trading_date"] == _d(300) and body["rows"][-1]["trading_date"] == _d(1)   # the oldest date is dropped
    else:
        assert body["truncation_notice"] is None and "truncated" not in page
    assert page.count("<tr>") >= min(n, 300)


# ---------------------------------------------------------------- stored-row integrity per run

def test_integrity_match_in_both_runs_with_the_note(db, client):
    _two_runs(db, _bars(), _bars(revised_on=2))
    body = _api(client, "AAA")[1]
    for side in ("base", "other"):
        check = body["integrity"][side]
        assert (check["label"], check["state"], check["bars"], check["mismatched"]) == ("stored-row integrity", "MATCH", 5, [])
        assert check["detail"] == "all 5 stored bars reproduce their stored hash"
    page = _page(client, "AAA")[1]
    assert "does not prove the vendor data is unchanged" in _text(_section(page, "integrity"))
    assert _text(re.search(r'<li id="integrity-base">.*?</li>', page, re.S).group(0)).startswith("Older run r-old: MATCH")


def test_integrity_mismatch_names_the_dates_in_the_run_where_a_stored_row_does_not_reproduce_its_hash(db, client, monkeypatch):
    _with_stored_hash(monkeypatch, db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())], {_d(1): "a" * 64, _d(3): "b" * 64})
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars())])
    body = _api(client, "AAA")[1]
    assert body["integrity"]["base"]["state"] == "MISMATCH" and body["integrity"]["base"]["mismatched"] == [_d(1), _d(3)]
    assert body["integrity"]["base"]["detail"] == f"2 of 5 stored bars do not reproduce their stored hash ({_d(1)}, {_d(3)})"
    assert body["integrity"]["other"]["state"] == "MATCH"
    assert 'class="integrity-state bad">MISMATCH' in _page(client, "AAA")[1]


def test_a_run_with_no_stored_bars_for_the_symbol_is_unavailable_never_match(db, client):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", [])])
    body = _api(client, "AAA")[1]
    assert body["integrity"]["other"]["state"] == "UNAVAILABLE" and body["integrity"]["other"]["bars"] == 0
    assert body["integrity"]["other"]["detail"] == "no stored bars to check" and body["integrity"]["base"]["state"] == "MATCH"
    assert body["state"] == "not_comparable" and body["reason"] == "no stored bars in the newer run"
    page = _page(client, "AAA")[1]
    assert re.search(r'<li id="integrity-other">.*?UNAVAILABLE', page, re.S) and "MATCH" not in _section(page, "integrity").split("integrity-other")[1]


def test_integrity_is_also_shown_for_a_symbol_present_in_one_run_only(db, client):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("BBB", "VALID", _bars())])
    body = _api(client, "AAA")[1]
    assert body["integrity"]["base"]["state"] == "MATCH"
    assert body["integrity"]["other"]["state"] == "UNAVAILABLE" and body["integrity"]["other"]["detail"] == "the symbol is not in this run"


# ---------------------------------------------------------------- the hash spy: exact counts

def _spy(monkeypatch):
    calls = []

    def wrap(module, name):
        original = getattr(module, name)
        monkeypatch.setattr(module, name, lambda *a, **k: calls.append(name) or original(*a, **k))

    wrap(stored_row_integrity, "compute_content_hash_from_stored_row")
    wrap(stored_row_integrity, "check_rows")
    wrap(snapshots, "compute_content_hash")
    wrap(stock_detail, "compute_content_hash_from_stored_row")
    return calls


def test_the_drill_down_recomputes_exactly_one_hash_per_stored_bar_of_this_symbol_in_each_run(db, client, monkeypatch):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars(n=5)), ("BBB", "VALID", _bars(n=4))])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars(n=7, revised_on=2)), ("BBB", "VALID", _bars(n=4)), ("CCC", "VALID", _bars(n=9))])
    calls = _spy(monkeypatch)
    assert _api(client, "AAA")[0].status_code == 200
    assert calls.count("compute_content_hash_from_stored_row") == 5 + 7 and calls.count("check_rows") == 2
    calls.clear()
    assert _page(client, "AAA")[0].status_code == 200
    assert calls.count("compute_content_hash_from_stored_row") == 12 and calls.count("check_rows") == 2
    calls.clear()
    _api(client, "BBB")
    assert calls.count("compute_content_hash_from_stored_row") == 4 + 4
    calls.clear()
    _api(client, "CCC")                                    # present in the newer run only: its 9 bars, none from the older run
    assert calls.count("compute_content_hash_from_stored_row") == 9
    calls.clear()
    assert _api(client, "NOPE")[0].status_code == 404
    assert calls.count("compute_content_hash_from_stored_row") == 0
    assert "compute_content_hash" not in calls and "compute_content_hash_from_stored_row" not in [c for c in calls if c != "check_rows"]


def test_the_main_page_and_the_main_json_route_still_recompute_nothing(db, client, monkeypatch):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars(revised_on=2))])
    calls = _spy(monkeypatch)
    for url in (MAIN_API, MAIN_PAGE, MAIN_API + "?view=added", MAIN_PAGE + "?view=removed", MAIN_PAGE + "?base=x&other=y"):
        client.get(url)
    assert calls == []


def test_the_recompute_goes_through_check_rows_only(db):
    import inspect
    source = inspect.getsource(snapshot_audit)
    assert "hashlib" not in source and "compute_content_hash" not in source and "sha256" not in source.lower()
    assert source.count("check_rows(") == 1


# ---------------------------------------------------------------- edge cases

def test_a_symbol_in_neither_run_is_a_404_message_page_with_the_symbol_escaped(db, client):
    _three_runs(db)
    res, page = _page(client, "<script>x")
    assert res.status_code == 404 and "<h1>Symbol not found</h1>" in page
    assert "<script>x" not in page and "&lt;script&gt;x" in page
    assert "Traceback" not in page and "<table" not in page
    res, body = _api(client, "NOPE")
    assert res.status_code == 404 and body["state"] == "absent" and body["message"] == "symbol NOPE is in neither run (r2 nor r3)"


def test_a_symbol_added_in_the_newer_run_only_says_so_and_has_no_bar_tables(db, client):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars()), ("NEW", "VALID", _bars())])
    res, body = _api(client, "NEW")
    assert res.status_code == 200 and body["state"] == "added" and body["counts"] is None and body["rows"] == []
    assert body["message"] == "NEW was added: it is in the newer run r-new but not in the older run r-old. There is nothing to compare bar by bar."
    page = _page(client, "NEW")[1]
    assert "NEW was added" in _text(_section(page, "state"))
    for absent in ('id="differing-bars"', 'id="counts"', 'id="results"'):
        assert absent not in page


def test_a_symbol_removed_from_the_newer_run_says_so_and_has_no_bar_tables(db, client):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars()), ("GONE", "VALID", _bars())])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars())])
    body = _api(client, "GONE")[1]
    assert body["state"] == "removed" and "GONE was removed: it is in the older run r-old but not in the newer run r-new" in body["message"]
    page = _page(client, "GONE")[1]
    assert "GONE was removed" in _text(_section(page, "state")) and 'id="differing-bars"' not in page
    assert body["company_name"] == "GONE Co"


@pytest.mark.parametrize("old_status, new_status, expected", [
    ("VALID", "FAILED", "FAILED in the newer run"),
    ("FAILED", "VALID", "FAILED in the older run"),
    ("FAILED", "FAILED", "FAILED in the older run; FAILED in the newer run"),
])
def test_a_failed_symbol_is_not_comparable_with_the_reason(db, client, old_status, new_status, expected):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", old_status, [] if old_status == "FAILED" else _bars())])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", new_status, [] if new_status == "FAILED" else _bars())])
    body = _api(client, "AAA")[1]
    assert body["state"] == "not_comparable" and body["reason"] == expected and body["rows"] == [] and body["counts"] is None
    page = _page(client, "AAA")[1]
    assert f"AAA cannot be compared bar by bar: {expected}." in _text(_section(page, "state"))
    assert 'id="differing-bars"' not in page


def test_no_stored_bars_in_either_run_is_not_comparable(db, client):
    _two_runs(db, [], [])
    body = _api(client, "AAA")[1]
    assert body["state"] == "not_comparable" and body["reason"] == "no stored bars in the older run; no stored bars in the newer run"
    assert body["integrity"]["base"]["state"] == body["integrity"]["other"]["state"] == "UNAVAILABLE"


def test_fewer_than_two_eligible_runs_is_an_explicit_message_not_an_error(db, client):
    _make_run(db, "only", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    res, body = _api(client, "AAA")
    assert res.status_code == 200 and body["comparison_available"] is False
    assert body["message"] == "a comparison needs two COMPLETE full runs; found 1" and body["state"] is None
    res, page = _page(client, "AAA")
    assert res.status_code == 200 and "a comparison needs two COMPLETE full runs; found 1" in _text(page)


def test_a_missing_database_is_a_message_page(tmp_path, monkeypatch):
    from equity_intel.persistence import db_path_guard
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", tmp_path / "absent.db")
    res = create_app(demo=False, db_path=tmp_path / "absent.db").test_client().get(PAGE + "AAA")
    assert res.status_code == 200 and "No scans yet" in res.get_data(as_text=True)
    assert create_app(demo=False, db_path=tmp_path / "absent.db").test_client().get(API + "AAA").status_code == 200


# ---------------------------------------------------------------- run selection: same rules and messages as the main page

@pytest.mark.parametrize("query", ["base=r1", "other=r3", "base=r1&other=r1", "base=nope&other=r1", "base=r1&other=nope",
                                   "base=r-abort&other=r3", "base=r1&other=r-run", "base=r-smoke&other=r3", "base=" + "z" * 101 + "&other=r1"])
def test_run_selection_errors_are_the_same_400_texts_as_the_main_route(db, client, query):
    _three_runs(db)
    _make_run(db, "r-abort", "2026-09-05T09:00:00", end="ABORTED")
    _make_run(db, "r-run", "2026-09-05T10:00:00", end="RUNNING")
    _make_run(db, "r-smoke", "2026-09-05T11:00:00", [("AAA", "VALID", [])], smoke=json.dumps(["AAA"]))
    main = client.get(f"{MAIN_API}?{query}")
    res, body = _api(client, "AAA", query)
    assert main.status_code == res.status_code == 400 and body == main.get_json()
    page_res, page = _page(client, "AAA", query)
    assert page_res.status_code == 400 and "<h1>Invalid parameter</h1>" in page and "<table" not in page
    assert body["error"] in _text(page)


def test_script_text_in_base_is_escaped_in_the_400_page(db, client):
    _three_runs(db)
    res, page = _page(client, "AAA", "base=%3Cscript%3Ex%3C%2Fscript%3E&other=r3")
    assert res.status_code == 400 and "<script" not in page and "&lt;script&gt;x&lt;/script&gt;" in page


def test_default_pair_and_explicit_pair_and_swap_are_the_main_pages_rules(db, client):
    _three_runs(db)
    body = _api(client, "AAA")[1]
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r2", "r3") and body["swapped"] is False
    body = _api(client, "AAA", "base=r1&other=r3")[1]
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"], body["counts"]["differing_bars"]) == ("r1", "r3", 1)
    swapped = _api(client, "AAA", "base=r3&other=r1")[1]
    assert swapped["swapped"] is True and (swapped["base_run"]["run_id"], swapped["other_run"]["run_id"]) == ("r1", "r3")
    page = _page(client, "AAA", "base=r3&other=r1")[1]
    assert "base (r3) is newer than other (r1)" in _text(re.search(r'<p class="notice" id="swap-note">.*?</p>', page, re.S).group(0))


def test_run_selection_and_other_parameters(db, client):
    _three_runs(db)
    body = _api(client, "AAA", "run_id=r1&view=nonsense&page=9")[1]       # the drill-down takes only base and other
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r2", "r3") and set(body["params"]) == {"base", "other"}


# ---------------------------------------------------------------- links

def test_every_link_on_the_drill_down_page_carries_the_resolved_pair_and_works(db, client):
    _three_runs(db)
    page = _page(client, "AAA", "base=r1&other=r3")[1]
    own = [h for h in _hrefs(page) if h.startswith(MAIN_PAGE) and h != MAIN_PAGE]  # h != MAIN_PAGE skips the bare header nav link
    assert own
    for href in own:
        assert parse_qs(urlsplit(href).query) == {"base": ["r1"], "other": ["r3"]}, href
        assert client.get(href).status_code == 200, href
    assert "/equity/stock/AAA" in _hrefs(page)
    default = _page(client, "AAA")[1]
    assert all(parse_qs(urlsplit(h).query) == {"base": ["r2"], "other": ["r3"]} for h in _hrefs(default) if h.startswith(MAIN_PAGE) and h != MAIN_PAGE)


def test_the_builder_rows_carry_a_drilldown_url_for_the_revised_view_only(db, client):
    _three_runs(db)
    row = client.get(MAIN_API).get_json()["rows"][0]
    assert row["drilldown_url"] == "/equity/snapshot-audit/symbol/AAA?base=r2&other=r3"
    assert all("drilldown_url" not in r for r in client.get(MAIN_API + "?view=added").get_json()["rows"])
    assert all("drilldown_url" not in r for r in client.get(MAIN_API + "?view=removed").get_json()["rows"])


def test_symbols_with_special_characters_round_trip_through_the_drilldown_url(db, client):
    old = [("A&B 50%", "VALID", _bars(), "Odd Co", "IT")]
    new = [("A&B 50%", "VALID", _bars(revised_on=1), "Odd Co", "IT")]
    _make_run(db, "r-old", "2026-09-01T09:00:00", old)
    _make_run(db, "r-new", "2026-09-02T09:00:00", new)
    href = client.get(MAIN_API).get_json()["rows"][0]["drilldown_url"]
    assert client.get(href).status_code == 200 and "A&amp;B 50%" in client.get(href).get_data(as_text=True)
    res = client.get(href.replace("/equity/snapshot-audit", "/api/equity/snapshot-audit", 1))
    assert res.status_code == 200 and res.get_json()["symbol"] == "A&B 50%" and res.get_json()["state"] == "comparable"


# ---------------------------------------------------------------- symbol text, methods, parity

@pytest.mark.parametrize("symbol", ["<script>alert(1)</script>", "'; DROP TABLE scan_runs; --", "%25_%25", "Ünï-çødé", "रिलायंस", "A" * 100])
def test_odd_symbol_text_is_looked_up_safely_and_escaped(db, client, symbol):
    _three_runs(db)
    res, page = _page(client, symbol)
    assert res.status_code == 404 and "<script" not in page and "Traceback" not in page
    if "/" not in symbol:                       # a slash never reaches the route: the generic 404 page has no user text
        assert symbol in html.unescape(page) and "<h1>Symbol not found</h1>" in page
    assert _api(client, symbol)[0].status_code == 404
    assert client.get(MAIN_API).status_code == 200      # nothing was damaged


def test_a_symbol_over_100_characters_is_a_400_on_both_routes(db, client):
    _three_runs(db)
    long_symbol = "S" * 101
    res, body = _api(client, long_symbol)
    assert res.status_code == 400 and body == {"error": "symbol must be at most 100 characters"}
    res, page = _page(client, long_symbol)
    assert res.status_code == 400 and "symbol must be at most 100 characters" in page and long_symbol not in page


def test_company_and_sector_text_from_the_database_is_escaped(db, client):
    _two_runs(db, _bars(), _bars(revised_on=1), name="<b>Bold</b> & Co", sector="<i>IT</i>")
    page = _page(client, "AAA")[1]
    assert "<b>Bold</b>" not in page and "&lt;b&gt;Bold&lt;/b&gt; &amp; Co" in page and "<i>IT</i>" not in page


@pytest.mark.parametrize("base_url", [PAGE, API])
def test_post_put_delete_and_patch_are_405(db, client, base_url):
    _three_runs(db)
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)(base_url + "AAA").status_code == 405, method


def test_html_and_json_show_the_same_dates_counts_and_integrity(db, client):
    _two_runs(db, _bars(n=8), [(_d(i), 100.0 + i + (0.5 if i in (2, 5, 6) else 0.0)) for i in range(8)])
    body = _api(client, "AAA")[1]
    page = _page(client, "AAA")[1]
    shown = re.findall(r"<tr>\s*<td>(\d{4}-\d{2}-\d{2})</td>", page)
    assert shown == [r["trading_date"] for r in body["rows"]] == [_d(6), _d(5), _d(2)]
    visible = _text(page)
    for line in body["counts_text"].values():
        assert line in visible
    for side in ("base", "other"):
        assert body["integrity"][side]["detail"] in _text(re.search(rf'<li id="integrity-{side}">.*?</li>', page, re.S).group(0))


# ---------------------------------------------------------------- read-only, secrets, wording

def test_requests_never_modify_the_database_file(db, client):
    _two_runs(db, _bars(), _bars(revised_on=2))
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    for url in (PAGE + "AAA", API + "AAA", PAGE + "NOPE", API + "NOPE", PAGE + "AAA?base=x&other=y", API + "AAA?base=r-old", PAGE + "A" * 101):
        client.get(url)
    client.post(PAGE + "AAA")
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_the_drill_down_reads_through_a_read_only_connection(db, monkeypatch):
    import sqlite3
    _two_runs(db, _bars(), _bars(revised_on=2))
    seen = []
    real = snapshot_audit.build_symbol

    def spying(conn, params, symbol):
        for statement in ("CREATE TABLE should_not_exist (x)", "UPDATE price_fetch_snapshots SET close = '1.00'",
                          "DELETE FROM symbol_scan_results", "DROP TABLE scan_runs"):
            try:
                conn.execute(statement)
                seen.append("WRITE ALLOWED: " + statement)
            except sqlite3.OperationalError:
                seen.append("rejected")
        return real(conn, params, symbol)

    monkeypatch.setattr(snapshot_audit, "build_symbol", spying)
    test_client = create_app(demo=False, db_path=db).test_client()
    assert test_client.get(API + "AAA").status_code == 200 and test_client.get(PAGE + "AAA").status_code == 200
    assert seen == ["rejected"] * 8


def test_no_env_token_script_chart_or_ranking_wording_on_any_state(db, client):
    _two_runs(db, _bars(), _bars(revised_on=2))
    _make_run(db, "r-x", "2026-09-03T09:00:00", [("AAA", "FAILED", []), ("ONLYNEW", "VALID", _bars())])
    for url in (PAGE + "AAA?base=r-old&other=r-new", PAGE + "AAA?base=r-new&other=r-x", PAGE + "ONLYNEW?base=r-new&other=r-x", PAGE + "NOPE"):
        page = client.get(url).get_data(as_text=True)
        for forbidden in (".env", "UPSTOX", "access_token", "ACCESS_TOKEN", "api_key", "Bearer"):
            assert forbidden not in page, forbidden
        assert "<script" not in page.lower() and "<canvas" not in page and "<svg" not in page and "<img" not in page
        assert not re.findall(r'(?:src|href)="(?:https?:)?//', page)
        visible = _text(page.split("<main>", 1)[1]).lower()
        assert not re.search(r"\b(score|scores|scored|rank|ranks|ranked|ranking|signal|signals|buy|sell|target|targets|stop-?loss|"
                             r"confidence|top picks?|best|worst|strongest|weakest|because|caused|due to)\b", visible), url
    body = client.get(API + "AAA?base=r-old&other=r-new").get_data(as_text=True)
    for forbidden in (".env", "UPSTOX", "access_token", "Bearer"):
        assert forbidden not in body
    keys = set(re.findall(r'"([a-z_]+)":', body))
    assert not any(re.search(r"score|rank|signal|target|stop_?loss|confidence|chart|cause", k) for k in keys), keys


def test_the_template_has_no_safe_filter_and_is_lf_without_bom():
    from equity_intel.tests.test_dashboard_no_unsafe_markup import _files
    template = next(p for p in _files("*.html") if p.name == "snapshot_audit_symbol.html")
    raw = template.read_bytes()
    assert not re.search(rb"\|\s*safe\b", raw) and not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw


def test_the_new_helpers_run_only_selects(db):
    conn = connection.get_read_only_connection(db)
    try:
        _two_runs_ro = queries.get_stored_bars(conn, "nope", "AAA")
        assert _two_runs_ro == []
    finally:
        conn.close()


# ---------------------------------------------------------------- get_symbol_revisions(newest_first) and get_stored_bars

def test_newest_first_is_optional_and_the_default_order_is_unchanged(db):
    _differing_bars(db, 5)
    conn = connection.get_read_only_connection(db)
    try:
        oldest = queries.get_symbol_revisions(conn, "r-old", "r-new", "AAA")
        newest = queries.get_symbol_revisions(conn, "r-old", "r-new", "AAA", newest_first=True)
        capped = queries.get_symbol_revisions(conn, "r-old", "r-new", "AAA", limit=2, newest_first=True)
    finally:
        conn.close()
    assert [r["trading_date"] for r in oldest["rows"]] == [_d(i) for i in range(5)]
    assert [r["trading_date"] for r in newest["rows"]] == [_d(i) for i in reversed(range(5))]
    assert [r["trading_date"] for r in capped["rows"]] == [_d(4), _d(3)] and capped["truncated"] is True and capped["differing"] == 5


def test_get_stored_bars_returns_only_this_symbol_in_this_run_oldest_first(db):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars(n=3)), ("BBB", "VALID", _bars(n=2))])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars(n=4))])
    conn = connection.get_read_only_connection(db)
    try:
        rows = queries.get_stored_bars(conn, "r-old", "AAA")
        assert [r["trading_date"] for r in rows] == [_d(0), _d(1), _d(2)] and len(queries.get_stored_bars(conn, "r-new", "AAA")) == 4
        assert set(rows[0]) == {"trading_date", "source", "open", "high", "low", "close", "volume", "content_hash"}
        assert queries.get_stored_bars(conn, "r-old", "A%") == [] and queries.get_stored_bars(conn, "r-old", "AAA' OR '1'='1") == []
    finally:
        conn.close()


# ---------------------------------------------------------------- the demo seed

def _demo_expected():
    """Per non-FAILED demo symbol: (index, symbol, expected differing fields), derived from the seed's own rule functions."""
    out = []
    for i, (symbol, _name, _sector, status, *_rest) in enumerate(seed.FAKE_SYMBOLS):
        if status == "FAILED" or seed.REVISED_DATE not in seed._bar_dates_for(status):
            continue
        old, new = seed._bar_values(i, seed.REVISED_DATE, revised=False), seed._bar_values(i, seed.REVISED_DATE, revised=True)
        fields = (["open", "high", "low", "close"] if old[0] != new[0] else []) + (["volume"] if old[1] != new[1] else [])
        out.append((i, symbol, status, old, new, fields))
    return out


def test_demo_drilldown_matches_the_seed_constants(demo_db):
    client = create_app(demo=True, db_path=demo_db).test_client()
    expected = _demo_expected()
    revised = [e for e in expected if e[5]]
    unrevised = [e for e in expected if not e[5]]
    assert revised and unrevised
    for i, symbol, status, old, new, fields in revised:
        body = client.get(API + symbol).get_json()
        assert body["state"] == "comparable" and body["demo"] is True
        assert body["counts"]["overlapping_bars"] == len(seed._bar_dates_for(status)) and body["counts"]["differing_bars"] == 1
        (row,) = body["rows"]
        assert row["trading_date"] == seed.REVISED_DATE and row["differing_fields"] == fields
        assert row["base"]["close"] == f"{old[0]:.2f}" and row["other"]["close"] == f"{new[0]:.2f}"
        assert (row["base"]["volume"], row["other"]["volume"]) == (old[1], new[1])
        assert body["integrity"]["base"]["state"] == body["integrity"]["other"]["state"] == "MATCH"
        assert body["integrity"]["other"]["bars"] == len(seed._bar_dates_for(status))
    for i, symbol, status, *_ in unrevised:
        body = client.get(API + symbol).get_json()
        assert body["counts"]["differing_bars"] == 0 and body["rows"] == []


def test_demo_failed_symbols_are_not_comparable_and_the_ineligible_runs_cannot_be_chosen(demo_db):
    client = create_app(demo=True, db_path=demo_db).test_client()
    failed = [s[0] for s in seed.FAKE_SYMBOLS if s[3] == "FAILED"]
    assert failed
    for symbol in failed:
        body = client.get(API + symbol).get_json()
        assert body["state"] == "not_comparable" and "FAILED" in body["reason"]
        assert body["integrity"]["base"]["state"] == body["integrity"]["other"]["state"] == "UNAVAILABLE"
    res = client.get(API + f"{seed.FAKE_SYMBOLS[0][0]}?base=r-demo-prev-complete&other=r-demo-aborted")
    assert res.status_code == 400 and "r-demo-aborted is not a COMPLETE full run (ABORTED)" in res.get_json()["error"]

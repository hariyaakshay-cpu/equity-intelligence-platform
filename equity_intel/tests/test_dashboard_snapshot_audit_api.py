"""GET /api/equity/snapshot-audit and dashboard.snapshot_audit: run selection, views, parameters, notes, safety.

Runs are built per case in tmp_path databases by the helpers of test_dashboard_snapshot_audit_queries.py (the
scanner's own snapshot writer, so stored hashes are real). Demo expectations are derived from the seed's constants.
"""
import hashlib
import inspect
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from dashboard import queries, snapshot_audit, stock_detail, stored_row_integrity
from dashboard.app import create_app
from equity_intel.persistence import connection
from equity_intel.scanner import snapshots
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _d, _make_run
from equity_intel.tests.test_dashboard_snapshot_audit_queries import demo_db  # noqa: F401  (fixture)
from scripts import dashboard_demo_seed as seed

API = "/api/equity/snapshot-audit"


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def _get(client, query=""):
    res = client.get(API + (("?" + query) if query else ""))
    return res, res.get_json()


def _bars(revised_on=None, n=5):
    return [(_d(i), 100.0 + i + (0.5 if i == revised_on else 0.0)) for i in range(n)]


def _make_versioned_run(db, run_id, started_at, symbols, *, universe, review, git):
    """A COMPLETE full run whose universe_version, review version and git_commit are chosen by the test."""
    _make_run(db, run_id, started_at, symbols, end="RUNNING")
    failed = sum(1 for s in symbols if s[1] == "FAILED")
    conn = connection.get_connection(db)
    try:
        conn.execute(
            "UPDATE scan_runs SET status = 'COMPLETE', finished_at = ?, latest_closed_session = '2026-10-01', "
            "universe_version = ?, corporate_action_review_version = ?, price_source = 't', benchmark = 'B', "
            "calendar_source = 'c', calendar_verification = 'UNVERIFIED_INDEX_ONLY', requested_symbols = ?, "
            "successful_symbols = ?, failed_symbols = ?, status_counts_json = ?, flag_counts_json = ?, git_commit = ?, "
            "git_dirty = 0 WHERE run_id = ?",
            (started_at, universe, review, len(symbols), len(symbols) - failed, failed,
             json.dumps({s: sum(1 for x in symbols if x[1] == s) for s in queries.STATUS_VALUES}),
             json.dumps({}), git, run_id))
        conn.commit()
    finally:
        conn.close()


def _three_runs(db):
    for n in (1, 2, 3):
        _make_run(db, f"r{n}", f"2026-09-0{n}T09:00:00", [("AAA", "VALID", _bars(revised_on=n if n > 1 else None))])


# ---------------------------------------------------------------- the default pair and explicit pairs

def test_default_pair_is_the_latest_eligible_run_as_newer_and_the_previous_complete_run_as_older(db, client):
    _three_runs(db)
    _make_run(db, "r-abort", "2026-09-05T09:00:00", end="ABORTED")
    _make_run(db, "r-smoke", "2026-09-06T09:00:00", [("AAA", "VALID", [])], smoke=json.dumps(["AAA"]))
    res, body = _get(client)
    assert res.status_code == 200 and body["comparison_available"] is True and body["message"] is None
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r2", "r3")
    assert body["swapped"] is False and body["swap_note"] is None
    conn = connection.get_read_only_connection(db)
    try:
        assert queries.get_previous_complete_run(conn, queries.get_latest_complete_run(conn))["run_id"] == "r2"
    finally:
        conn.close()
    assert body["scoring_status"] == "BLOCKED_B2" and body["layer"] == "ScanRun"


def test_explicit_pair_can_be_any_two_eligible_runs(db, client):
    _three_runs(db)
    res, body = _get(client, "base=r1&other=r3")
    assert res.status_code == 200 and (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r1", "r3")
    assert body["counts"]["differing_bars"] == 1 and body["params"]["base"] == "r1"
    other = _get(client, "base=r1&other=r2")[1]
    assert (other["base_run"]["run_id"], other["other_run"]["run_id"]) == ("r1", "r2")


def test_reversed_base_and_other_are_swapped_with_a_visible_note(db, client):
    _three_runs(db)
    res, body = _get(client, "base=r3&other=r1")
    assert res.status_code == 200 and body["swapped"] is True
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r1", "r3")  # older is always the base
    note = body["swap_note"]
    assert "base (r3) is newer than other (r1)" in note and "swapped" in note
    assert "the older run r1 is used as base and the newer run r3 as other" in note
    in_order = _get(client, "base=r1&other=r3")[1]
    assert in_order["swapped"] is False and in_order["swap_note"] is None
    assert in_order["counts"] == body["counts"] and in_order["rows"] == body["rows"]   # the same comparison either way


def test_equal_started_at_is_ordered_by_run_id_and_swapped_consistently(db, client):
    _make_run(db, "r-a", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-b", "2026-09-01T09:00:00", [("AAA", "VALID", _bars(revised_on=2))])
    forward = _get(client, "base=r-a&other=r-b")[1]
    backward = _get(client, "base=r-b&other=r-a")[1]
    assert (forward["base_run"]["run_id"], forward["other_run"]["run_id"]) == ("r-a", "r-b") and forward["swapped"] is False
    assert (backward["base_run"]["run_id"], backward["other_run"]["run_id"]) == ("r-a", "r-b") and backward["swapped"] is True
    default = _get(client)[1]
    assert (default["base_run"]["run_id"], default["other_run"]["run_id"]) == ("r-a", "r-b")  # two eligible runs are found


# ---------------------------------------------------------------- base / other validation

@pytest.mark.parametrize("which", ["base", "other"])
@pytest.mark.parametrize("kind, label", [("ABORTED", "ABORTED"), ("RUNNING", "RUNNING"), ("SMOKE", "smoke run, --symbols")])
def test_ineligible_runs_passed_as_base_or_other_give_400_naming_the_run_and_why(db, client, which, kind, label):
    _three_runs(db)
    if kind == "ABORTED":
        _make_run(db, "r-bad", "2026-09-05T09:00:00", end="ABORTED")
    elif kind == "RUNNING":
        _make_run(db, "r-bad", "2026-09-05T09:00:00", end="RUNNING")
    else:
        _make_run(db, "r-bad", "2026-09-05T09:00:00", [("AAA", "VALID", [])], smoke=json.dumps(["AAA"]))
    query = "base=r-bad&other=r3" if which == "base" else "base=r1&other=r-bad"
    res, body = _get(client, query)
    assert res.status_code == 400 and set(body) == {"error"}
    assert body["error"] == f"run r-bad is not a COMPLETE full run ({label})"


def test_unknown_identical_and_half_given_runs_give_400(db, client):
    _three_runs(db)
    assert _get(client, "base=r1&other=nope")[1]["error"] == "run nope does not exist"
    assert _get(client, "base=nope&other=r1")[1]["error"] == "run nope does not exist"
    res, body = _get(client, "base=r1&other=r1")
    assert res.status_code == 400 and "base and other are the same run (r1)" in body["error"]
    for query in ("base=r1", "other=r3"):
        res, body = _get(client, query)
        assert res.status_code == 400 and "must be given together" in body["error"], query
    injected = _get(client, "base=r1%27%20OR%20%271%27%3D%271&other=r3")
    assert injected[0].status_code == 400 and "does not exist" in injected[1]["error"]


# ---------------------------------------------------------------- fewer than two eligible runs

@pytest.mark.parametrize("n_complete", [0, 1])
def test_fewer_than_two_eligible_runs_is_an_explicit_message_never_no_changes(db, client, n_complete):
    if n_complete:
        _make_run(db, "only", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())])
    _make_run(db, "r-abort", "2026-09-02T09:00:00", end="ABORTED")
    _make_run(db, "r-smoke", "2026-09-03T09:00:00", [("AAA", "VALID", [])], smoke=json.dumps(["AAA"]))
    res, body = _get(client)
    assert res.status_code == 200 and body["comparison_available"] is False
    assert body["message"] == f"a comparison needs two COMPLETE full runs; found {n_complete}"
    assert body["counts"] is None and body["rows"] == [] and body["views"] is None
    assert "no changes" not in json.dumps(body).lower() and "0 revisions" not in json.dumps(body).lower()
    assert body["eligible_runs"]["total"] == n_complete and body["ineligible_runs"]["total"] == 2  # still listed
    assert body["metric"]["name"] == "bars whose stored hash differs"
    assert snapshot_audit.page_links(body) is None


def test_an_empty_database_with_no_runs_at_all_is_the_same_explicit_message(db, client):
    res, body = _get(client)
    assert res.status_code == 200 and body["message"] == "a comparison needs two COMPLETE full runs; found 0"


# ---------------------------------------------------------------- what the response carries

def test_response_carries_both_runs_notes_lists_counts_and_the_metric_wording(db, client):
    _make_versioned_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())], universe="uv-OLD", review="rv-OLD", git="git-OLD")
    _make_versioned_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars(revised_on=2))], universe="uv-NEW", review="rv-NEW", git="git-NEW")
    _make_run(db, "r-abort", "2026-09-03T09:00:00", end="ABORTED")
    body = _get(client)[1]
    for key, run_id in (("base_run", "r-old"), ("other_run", "r-new")):
        run = body[key]
        assert run["run_id"] == run_id and run["started_at"] and run["finished_at"]
        assert set(run) == {"run_id", "started_at", "finished_at", "latest_closed_session", "universe_version",
                            "corporate_action_review_version", "git_commit"}
    assert (body["base_run"]["universe_version"], body["other_run"]["git_commit"]) == ("uv-OLD", "git-NEW")
    notes = body["comparability_notes"]
    assert len(notes) == 4
    assert "universe_version differs between the two runs (uv-OLD vs uv-NEW)" in notes[0]
    assert "corporate_action_review_version differs" in notes[1] and "git_commit differs" in notes[2]
    assert notes[-1] == snapshot_audit.NO_HASH_VERSION_NOTE and "records no hash or quantisation version" in notes[-1]
    assert body["metric"]["name"] == "bars whose stored hash differs"
    note = body["metric"]["note"]
    assert "possible vendor revision" in note and "does not classify the cause" in note and "NOT_DEFINED" in note
    assert body["newer_run"]["run_id"] == "r-abort" and "ABORTED" in body["newer_run"]["reason"]
    assert body["ineligible_runs"]["runs"][0]["run_id"] == "r-abort" and body["ineligible_runs"]["more"] == 0
    assert [r["run_id"] for r in body["eligible_runs"]["runs"]] == ["r-new", "r-old"]


def test_only_the_fixed_hash_note_when_nothing_else_differs(db, client):
    _make_versioned_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars())], universe="u", review="r", git="g")
    _make_versioned_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars())], universe="u", review="r", git="g")
    assert _get(client)[1]["comparability_notes"] == [snapshot_audit.NO_HASH_VERSION_NOTE]


def test_aborted_run_newer_than_the_latest_complete_run_is_excluded_from_the_pair_and_bannered(db, client):
    _three_runs(db)
    _make_run(db, "r-abort", "2026-09-09T09:00:00", [("AAA", "VALID", _bars(revised_on=1))], end="ABORTED")
    body = _get(client)[1]
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r2", "r3")
    assert body["newer_run"]["run_id"] == "r-abort" and "ABORTED" in body["newer_run"]["reason"]
    assert "r-abort" not in {r["run_id"] for r in body["eligible_runs"]["runs"]}
    assert "r-abort" in {r["run_id"] for r in body["ineligible_runs"]["runs"]}


def test_ineligible_list_is_the_newest_twenty_with_a_count_of_the_rest(db, client):
    _three_runs(db)
    for i in range(23):
        _make_run(db, f"r-abort-{i:02d}", f"2026-08-{i + 1:02d}T09:00:00", end="ABORTED")
    listed = _get(client)[1]["ineligible_runs"]
    assert listed["total"] == 23 and len(listed["runs"]) == 20 and listed["more"] == 3


# ---------------------------------------------------------------- the views

def _view_runs(db):
    names = {"R1": ("Alpha 50% Co", "IT"), "R2": ("AB_CD Ltd", "Auto"), "R3": ("Zeta Corp", "IT"), "R4": ("Mid Corp", "Energy"),
             "R5": ("Beta Ltd", None), "R6": ("Gamma Ltd", "Auto"), "R7": ("Delta Ltd", "IT")}
    old = [(s, "VALID", _bars(), *names[s]) for s in names]
    new = [(s, "VALID", _bars(revised_on=2), *names[s]) for s in names]
    old += [("SAME", "VALID", _bars(), "Same Co", "IT"), ("FAILNEW", "VALID", _bars(), "Fail Co", "IT"), ("GONE", "VALID", _bars(), "Gone Ltd", "Auto")]
    new += [("SAME", "VALID", _bars(), "Same Co", "IT"), ("FAILNEW", "FAILED", [], "Fail Co", "IT"),
            ("NEW1", "VALID", _bars(), "New One", "IT"), ("NEW2", "VALID", _bars(), "50% New", "Auto")]
    _make_run(db, "r-old", "2026-09-01T09:00:00", old)
    _make_run(db, "r-new", "2026-09-02T09:00:00", new)


def _symbols(client, query):
    body = _get(client, query)[1]
    return [r["symbol"] for r in body["rows"]]


def test_counts_and_denominators_for_a_mixed_pair(db, client):
    _view_runs(db)
    body = _get(client)[1]
    c = body["counts"]
    assert c == {"symbols_base": 10, "symbols_other": 11, "added": 2, "removed": 1, "in_both": 9,
                 "comparable_symbols": 8, "not_comparable_symbols": 1, "overlapping_bars": 40, "differing_bars": 7,
                 "symbols_with_differing_bars": 7, "only_in_older": 0, "only_in_newer": 0}
    assert body["views"] == {"revised": 7, "added": 2, "removed": 1}
    t = body["counts_text"]
    assert t["differing"] == "7 of 40 overlapping bars differ (bars whose stored hash differs), across 8 comparable symbols"
    assert t["symbols_with_differing"] == "7 of 8 comparable symbols have at least one such bar"
    assert t["not_comparable"].startswith("1 of 9 symbols present in both runs cannot be compared bar by bar")
    assert t["one_sided"] == "0 bars are only in the older run and 0 are only in the newer run (comparable symbols only)"
    assert t["added_removed"] == "2 symbols added and 1 removed (9 in both runs)"
    assert "comparable symbols only" in body["one_sided_note"]


def test_revised_view_lists_comparable_symbols_whose_bars_differ(db, client):
    _view_runs(db)
    body = _get(client)[1]
    assert body["view"] == "revised" and body["total"] == 7
    assert [r["symbol"] for r in body["rows"]] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]   # not SAME, FAILNEW, GONE, NEW*
    row = body["rows"][0]
    assert (row["overlapping_bars"], row["differing_bars"]) == (5, 1)
    assert row["first_differing_date"] == row["last_differing_date"] == _d(2)
    assert row["stock_url"] == "/equity/stock/R1" and (row["bars_older_run"], row["bars_newer_run"]) == (5, 5)


def test_added_and_removed_views(db, client):
    _view_runs(db)
    added = _get(client, "view=added")[1]
    assert [r["symbol"] for r in added["rows"]] == ["NEW1", "NEW2"] and added["total"] == 2 and added["view"] == "added"
    assert {r["symbol"]: r["status"] for r in added["rows"]} == {"NEW1": "VALID", "NEW2": "VALID"}
    removed = _get(client, "view=removed")[1]
    assert [r["symbol"] for r in removed["rows"]] == ["GONE"] and removed["total"] == 1
    assert added["counts"] == removed["counts"] == _get(client)[1]["counts"]  # denominators do not depend on the view


def test_sorting_is_limited_to_symbol_company_and_sector_and_puts_missing_values_last(db, client):
    _view_runs(db)
    assert _symbols(client, "sort=symbol&dir=desc") == ["R7", "R6", "R5", "R4", "R3", "R2", "R1"]
    assert _symbols(client, "sort=company_name") == ["R2", "R1", "R5", "R7", "R6", "R4", "R3"]
    assert _symbols(client, "sort=company_name&dir=desc") == ["R3", "R4", "R6", "R7", "R5", "R1", "R2"]
    assert _symbols(client, "sort=sector") == ["R2", "R6", "R4", "R1", "R3", "R7", "R5"]      # no-sector last
    assert _symbols(client, "sort=sector&dir=desc") == ["R1", "R3", "R7", "R4", "R2", "R6", "R5"]  # still last
    assert _symbols(client, "view=added&sort=sector") == ["NEW2", "NEW1"]


def test_sector_and_q_filters_and_pagination(db, client):
    _view_runs(db)
    assert _symbols(client, "sector=Auto") == ["R2", "R6"] and _symbols(client, "sector=UNKNOWN") == ["R5"]
    assert _symbols(client, "q=alpha") == ["R1"] and _symbols(client, "q=R3") == ["R3"]
    assert _symbols(client, "view=added&sector=Auto") == ["NEW2"]
    pages = [_get(client, f"page={n}&page_size=3")[1] for n in (1, 2, 3, 4)]
    assert [[r["symbol"] for r in p["rows"]] for p in pages] == [["R1", "R2", "R3"], ["R4", "R5", "R6"], ["R7"], []]
    assert all(p["total"] == 7 and p["total_pages"] == 3 and p["page_size"] == 3 for p in pages)
    narrowed = _get(client, "sector=Auto&q=Gamma")[1]
    assert narrowed["total"] == 1 and narrowed["counts"]["differing_bars"] == 7  # the denominators ignore the filters


def test_percent_and_underscore_in_q_are_literal_in_every_view(db, client):
    _view_runs(db)
    assert _symbols(client, "q=%25") == ["R1"] and _symbols(client, "q=_") == ["R2"] and _symbols(client, "q=AB_CD") == ["R2"]
    assert _symbols(client, "view=added&q=%25") == ["NEW2"] and _symbols(client, "view=added&q=_") == []
    assert _symbols(client, "q=%5C") == [] and _symbols(client, "q=%27%3B%20DROP%20TABLE%20scan_runs%3B%20--") == []
    for nasty in ("%25%25", "__", "%00", "%5C%25"):
        for view in ("revised", "added", "removed"):
            assert client.get(f"{API}?view={view}&q={nasty}").status_code == 200, (view, nasty)


def test_zero_rows_always_state_the_denominators_never_a_bare_zero(db, client):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", _bars()), ("BBB", "VALID", _bars())])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", _bars()), ("BBB", "VALID", _bars())])
    revised = _get(client)[1]
    assert revised["rows"] == [] and revised["total"] == 0 and revised["total_pages"] == 0
    assert revised["notice"] == ("no comparable symbol has bars whose stored hash differs (10 overlapping bars were compared "
                                 "across 2 comparable symbols between run r-old and run r-new)")
    assert revised["counts_text"]["differing"].startswith("0 of 10 overlapping bars differ")
    added = _get(client, "view=added")[1]
    assert added["notice"] == ("no symbols were added between run r-old and run r-new "
                               "(2 symbols in the newer run, 2 in the older run)")
    filtered = _get(client, "q=zzz")[1]
    assert filtered["notice"].startswith("no comparable symbols match the current filters (10 overlapping bars")
    assert all(bad not in json.dumps([revised, added, filtered]).lower() for bad in ("no changes", "0 revisions", "0 issues"))


def test_runs_with_no_overlapping_date_say_zero_of_zero_not_no_revisions(db, client):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", [(_d(0), 100.0), (_d(1), 101.0)])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", [(_d(5), 100.0), (_d(6), 101.0), (_d(7), 102.0)])])
    body = _get(client)[1]
    assert body["counts_text"]["differing"].startswith("0 of 0 overlapping bars differ")
    assert body["counts_text"]["one_sided"].startswith("2 bars are only in the older run and 3 are only in the newer run")
    assert body["total"] == 0 and "0 overlapping bars were compared" in body["notice"]


def test_an_all_bars_differ_symbol_is_a_count_with_no_cause_in_the_response(db, client):
    # every overlapping bar is rewritten (the shape a vendor adjustment would take), under a neutral symbol name
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("ALLDIFF", "VALID", [(_d(i), 200.0 + i) for i in range(6)])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("ALLDIFF", "VALID", [(_d(i), 100.0 + i / 2) for i in range(6)])])
    body = _get(client)[1]
    (row,) = body["rows"]
    assert (row["overlapping_bars"], row["differing_bars"]) == (6, 6)
    text = json.dumps(body).lower()
    assert "cause" in text and body["metric"]["note"].count("does not classify the cause") == 1
    assert not re.search(r"split|bonus|adjusted|adjustment applied|corporate action detected", json.dumps(body["rows"]).lower())


# ---------------------------------------------------------------- invalid parameters and methods

@pytest.mark.parametrize("query", [
    "view=both", "view=REVISED", "sort=differing_bars", "sort=status", "sort=overlapping_bars", "sort=;DROP", "dir=up",
    "dir=ASC", "page=0", "page=-1", "page=abc", "page=1.5", "page_size=0", "page_size=201", "page_size=x",
    "q=" + "x" * 101, "sector=" + "y" * 101, "base=" + "z" * 101 + "&other=r1",
])
def test_invalid_parameter_values_give_400_with_a_plain_message(db, client, query):
    _three_runs(db)
    res, body = _get(client, query)
    assert res.status_code == 400 and res.mimetype == "application/json"
    assert set(body) == {"error"} and "Traceback" not in body["error"] and len(body["error"]) < 200


def test_post_put_delete_and_patch_are_405(db, client):
    _three_runs(db)
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)(API).status_code == 405, method


def test_unknown_parameter_names_such_as_run_id_do_not_select_a_run(db, client):
    _three_runs(db)
    _make_run(db, "r-abort", "2026-09-09T09:00:00", end="ABORTED")
    body = _get(client, "run_id=r-abort&scan=r1")[1]
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r2", "r3")
    assert "run_id" not in body["params"]


# ---------------------------------------------------------------- hashing, read-only, secrets, wording

def test_no_hash_function_is_called_on_the_route_for_any_view_or_pair(db, client, monkeypatch):
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
                  "base=r-old&other=r-late&q=R", "sort=sector&dir=desc&page=2&page_size=2"):
        assert client.get(f"{API}?{query}").status_code == 200, query
    assert calls == []
    body = _get(client)[1]
    assert not any("hash_check" in k or "integrity" in k for k in json.dumps(body).lower().split('"'))
    source = inspect.getsource(snapshot_audit)
    assert "hashlib" not in source and "compute_content_hash" not in source and "sha256" not in source.lower()


def test_requests_never_modify_the_database_file(db, client):
    _view_runs(db)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    for query in ("", "view=added", "view=removed", "base=r-new&other=r-old", "q=%25&sort=sector", "sort=bad", "base=r-old",
                  "base=nope&other=r-new", "page=9&page_size=2"):
        client.get(f"{API}?{query}")
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_the_route_reads_through_a_read_only_connection(db, monkeypatch):
    import sqlite3
    _view_runs(db)
    seen = []
    real_build = snapshot_audit.build

    def spying_build(conn, params):
        for statement in ("CREATE TABLE should_not_exist (x)", "UPDATE price_fetch_snapshots SET close = '1.00'",
                          "DELETE FROM symbol_scan_results", "DROP TABLE scan_runs"):
            try:
                conn.execute(statement)
                seen.append("WRITE ALLOWED: " + statement)
            except sqlite3.OperationalError:
                seen.append("rejected")
        return real_build(conn, params)

    monkeypatch.setattr(snapshot_audit, "build", spying_build)
    assert create_app(demo=False, db_path=db).test_client().get(API).status_code == 200
    assert seen == ["rejected"] * 4


def test_response_has_no_env_token_score_rank_signal_or_chart_content(db, client):
    _view_runs(db)
    texts = [client.get(f"{API}?{q}").get_data(as_text=True) for q in ("", "view=added", "view=removed", "base=r-new&other=r-old")]
    for text in texts:
        for forbidden in (".env", "UPSTOX", "access_token", "ACCESS_TOKEN", "api_key", "Bearer"):
            assert forbidden not in text, forbidden
    keys = set()

    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                keys.add(k.lower())
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(json.loads(texts[0]))
    assert not any(re.search(r"score|rank|signal|^buy$|^sell$|target|stop_?loss|confidence|chart|candle_series|plot", k) for k in keys), keys
    visible = " ".join(re.findall(r'"(?:notice|message|text|note)[a-z_]*":\s*"([^"]*)"', texts[0]) + [json.loads(texts[0])["metric"]["note"]]).lower()
    assert not re.search(r"\b(score|scores|rank|ranked|ranking|signal|signals|buy|sell|target|confidence|top picks?)\b", visible)


def test_demo_flag_is_reported(db):
    _view_runs(db)
    assert create_app(demo=True, db_path=db).test_client().get(API).get_json()["demo"] is True
    assert create_app(demo=False, db_path=db).test_client().get(API).get_json()["demo"] is False


# ---------------------------------------------------------------- the demo seed (expected numbers derived from the seed's constants)

def _demo_expectations():
    non_failed = [(i, s[0], s[3]) for i, s in enumerate(seed.FAKE_SYMBOLS) if s[3] != "FAILED"]
    revised = sorted(
        sym for i, sym, status in non_failed
        if seed.REVISED_DATE in seed._bar_dates_for(status)
        and seed._bar_values(i, seed.REVISED_DATE, revised=True) != seed._bar_values(i, seed.REVISED_DATE, revised=False))
    overlap = sum(len(seed._bar_dates_for(status)) for _i, _s, status in non_failed)
    return non_failed, revised, overlap


def test_demo_default_pair_matches_the_seeds_documented_revisions(demo_db):
    non_failed, revised, overlap = _demo_expectations()
    assert revised and overlap
    client = create_app(demo=True, db_path=demo_db).test_client()
    res, body = _get(client, "page_size=200")
    assert res.status_code == 200
    assert (body["base_run"]["run_id"], body["other_run"]["run_id"]) == ("r-demo-prev-complete", "r-demo-latest-complete")
    c = body["counts"]
    assert c["symbols_base"] == c["symbols_other"] == c["in_both"] == len(seed.FAKE_SYMBOLS) and (c["added"], c["removed"]) == (0, 0)
    assert c["comparable_symbols"] == len(non_failed) and c["not_comparable_symbols"] == len(seed.FAKE_SYMBOLS) - len(non_failed)
    assert (c["overlapping_bars"], c["differing_bars"], c["symbols_with_differing_bars"]) == (overlap, len(revised), len(revised))
    assert sorted(r["symbol"] for r in body["rows"]) == revised and body["total"] == len(revised)
    assert body["counts_text"]["differing"] == (f"{len(revised)} of {overlap} overlapping bars differ "
                                                f"(bars whose stored hash differs), across {len(non_failed)} comparable symbols")
    assert body["newer_run"]["run_id"] == "r-demo-smoke"                       # the newest non-complete run is bannered
    assert {r["run_id"]: r["kind"] for r in body["ineligible_runs"]["runs"]} == {
        "r-demo-smoke": "SMOKE", "r-demo-aborted": "ABORTED", "r-demo-running": "RUNNING"}
    assert [r["run_id"] for r in body["eligible_runs"]["runs"]] == [
        "r-demo-latest-complete", "r-demo-prev-complete", "r-demo-old-complete"]
    assert "DEMO" not in json.dumps(body["comparability_notes"])  # the demo database is not presented as real data
    assert body["demo"] is True


def test_demo_old_vs_previous_run_have_no_overlapping_date(demo_db):
    non_failed, _revised, _overlap = _demo_expectations()
    client = create_app(demo=True, db_path=demo_db).test_client()
    body = _get(client, "base=r-demo-old-complete&other=r-demo-prev-complete")[1]
    c = body["counts"]
    assert (c["overlapping_bars"], c["differing_bars"]) == (0, 0)
    assert c["only_in_older"] == len(non_failed)
    assert c["only_in_newer"] == sum(len(seed._bar_dates_for(status)) for _i, _s, status in non_failed)
    assert body["counts_text"]["differing"].startswith("0 of 0 overlapping bars differ") and body["total"] == 0


def test_demo_ineligible_runs_cannot_be_chosen(demo_db):
    client = create_app(demo=True, db_path=demo_db).test_client()
    for run_id, label in (("r-demo-aborted", "ABORTED"), ("r-demo-running", "RUNNING"), ("r-demo-smoke", "smoke run, --symbols")):
        res, body = _get(client, f"base={run_id}&other=r-demo-latest-complete")
        assert res.status_code == 400 and body["error"] == f"run {run_id} is not a COMPLETE full run ({label})"


# ---------------------------------------------------------------- links for the HTML page

def _query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_page_links_pin_the_resolved_pair_and_keep_every_non_default_value(db, client):
    _view_runs(db)
    # q=a and sector=IT match R1, R3 and R7: three rows, so page_size=1 gives three pages and page 2 has both neighbours
    body = _get(client, "base=r-new&other=r-old&view=revised&q=a&sector=IT&page=2&page_size=1&sort=company_name&dir=desc")[1]
    assert body["total"] == 3 and body["total_pages"] == 3
    links = snapshot_audit.page_links(body)
    pinned = {"base": "r-old", "other": "r-new"}   # swapped into order and pinned, even though the request was reversed
    assert _query(links["this_page"]) == {**pinned, "q": "a", "sector": "IT", "page": "2", "page_size": "1",
                                          "sort": "company_name", "dir": "desc"}
    assert _query(links["next"]) == {**_query(links["this_page"]), "page": "3"}
    assert _query(links["prev"]) == {k: v for k, v in _query(links["this_page"]).items() if k != "page"}
    assert _query(links["views"]["added"]) == {**pinned, "q": "a", "sector": "IT", "page_size": "1", "sort": "company_name",
                                               "dir": "desc", "view": "added"}   # a view change returns to page 1
    assert "view" not in _query(links["views"]["revised"]) and "page" not in _query(links["views"]["added"])
    assert _query(links["clear_filters"]) == {**pinned, "page_size": "1", "sort": "company_name", "dir": "desc"}
    assert set(links["sort"]) == {"symbol", "company_name", "sector"} and links["sort"]["company_name"]["active"] is True
    toggled = _query(links["sort"]["company_name"]["url"])                    # an active descending column toggles to ascending,
    assert toggled["sort"] == "company_name" and "dir" not in toggled          # and ascending is the default, so it is omitted
    assert _query(links["sort"]["sector"]["url"]).get("sort") == "sector" and "page" not in _query(links["sort"]["sector"]["url"])


def test_page_links_omit_next_on_the_last_page_and_prev_on_the_first(db, client):
    _view_runs(db)
    first = snapshot_audit.page_links(_get(client, "page_size=3")[1])
    last = snapshot_audit.page_links(_get(client, "page=3&page_size=3")[1])
    assert first["prev"] is None and first["next"] and last["next"] is None and last["prev"]


def test_page_url_encodes_special_characters_in_filters():
    params = snapshot_audit.parse_params({"q": "a b&c=d", "sector": "R&D"})
    url = snapshot_audit.page_url(params, "r1", "r2")
    assert _query(url) == {"base": "r1", "other": "r2", "q": "a b&c=d", "sector": "R&D"}
    assert "&c=d" not in url.split("q=")[1].split("&sector")[0]

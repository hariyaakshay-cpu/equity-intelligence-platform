"""GET /api/equity/exceptions and dashboard.exceptions: categories, parameters, markers, banners, escaping.

Every case builds its own runs in a tmp_path database (the DB guard's paths are monkeypatched by the
`db` fixture, never the real files).
"""
import hashlib
import json
import re

import pytest

from dashboard import exceptions, queries
from dashboard.app import create_app
from equity_intel.persistence import connection, db_path_guard
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from scripts import dashboard_demo_seed as seed

NO_FLAGS = {"history_gaps": False, "corporate_action_review": False, "price_break_detected": False, "non_eq_series": False}


def _flags(*names):
    return {**NO_FLAGS, **{n: True for n in names}}


def _run(db, run_id, started_at, rows, *, universe="uv-1", review="rv-1", end="COMPLETE", smoke=None):
    """rows: (symbol, status, flag_names[, company_name[, sector]]). Builds one run; COMPLETE stores true counts."""
    extra = {} if smoke is None else {"symbols_filter_json": json.dumps(smoke)}
    conn = connection.get_connection(db)
    try:
        seed._insert_scan_run(conn, run_id, started_at, **extra)
        for symbol, status, names, *rest in rows:
            name = rest[0] if rest else symbol + " Co"
            sector = rest[1] if len(rest) > 1 else "IT"
            seed._insert_symbol_result(conn, run_id, symbol, name, sector, status, None, _flags(*names))
        if end == "ABORTED":
            seed._abort_run(conn, run_id, started_at, "AUTH_FAILED", [])
        elif end == "COMPLETE":
            status_counts = {s: sum(1 for r in rows if r[1] == s) for s in queries.STATUS_VALUES}
            flag_counts = {k.upper(): sum(1 for r in rows if k in r[2]) for k in NO_FLAGS}
            failed = status_counts["FAILED"]
            conn.execute(
                "UPDATE scan_runs SET status = 'COMPLETE', finished_at = ?, latest_closed_session = '2026-10-01', "
                "universe_version = ?, corporate_action_review_version = ?, price_source = 't', benchmark = 'B', "
                "calendar_source = 'c', calendar_verification = 'UNVERIFIED_INDEX_ONLY', requested_symbols = ?, "
                "successful_symbols = ?, failed_symbols = ?, status_counts_json = ?, flag_counts_json = ?, "
                "git_commit = 'x', git_dirty = 0 WHERE run_id = ?",
                (started_at, universe, review, len(rows), len(rows) - failed, failed,
                 json.dumps(status_counts), json.dumps(flag_counts), run_id))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(db):
    return create_app(demo=False, db_path=db).test_client()


def _get(client, query=""):
    res = client.get("/api/equity/exceptions" + (("?" + query) if query else ""))
    return res, res.get_json()


# ---------------------------------------------------------------- the 7 categories

CATEGORY_ROWS = [
    ("AAA", "VALID", []),
    ("BBB", "VALID", ["history_gaps"]),
    ("CCC", "INSUFFICIENT_HISTORY", ["history_gaps", "price_break_detected"]),
    ("DDD", "STALE", ["corporate_action_review"]),
    ("EEE", "FAILED", ["non_eq_series"]),
    ("FFF", "FAILED", []),
    ("GGG", "VALID", ["non_eq_series"]),
]
EXPECTED = {
    "FAILED": ["EEE", "FFF"], "STALE": ["DDD"], "INSUFFICIENT_HISTORY": ["CCC"],
    "HISTORY_GAPS": ["BBB", "CCC"], "NON_EQ_SERIES": ["EEE", "GGG"],
    "PRICE_BREAK_DETECTED": ["CCC"], "CORPORATE_ACTION_REVIEW": ["DDD"],
}


@pytest.mark.parametrize("category", list(EXPECTED))
def test_every_category_returns_exactly_its_rows(db, client, category):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    res, body = _get(client, f"category={category}")
    assert res.status_code == 200
    assert [r["symbol"] for r in body["rows"]] == EXPECTED[category]
    assert body["total"] == len(EXPECTED[category]) and body["category"] == category
    assert body["category_counts"][category] == len(EXPECTED[category])


def test_default_category_is_failed_and_all_seven_are_listed(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    body = _get(client)[1]
    assert body["category"] == "FAILED" and [r["symbol"] for r in body["rows"]] == ["EEE", "FFF"]
    assert set(body["category_counts"]) == set(exceptions.CATEGORY_COLUMNS) and len(exceptions.CATEGORY_COLUMNS) == 7
    assert body["category_counts"] == {k: len(v) for k, v in EXPECTED.items()}


def test_category_table_uses_only_the_whitelisted_columns():
    for name, (kind, key, column) in exceptions.CATEGORY_COLUMNS.items():
        if kind == "flag":
            assert queries.FLAG_COLUMNS[key] == column and column.endswith("_flag")
        else:
            assert key in queries.STATUS_VALUES


def test_rows_carry_status_flags_link_and_no_score_fields(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    row = _get(client, "category=INSUFFICIENT_HISTORY")[1]["rows"][0]
    assert row["symbol"] == "CCC" and row["status"] == "INSUFFICIENT_HISTORY" and row["stock_url"] == "/equity/stock/CCC"
    assert row["flags"] == {"HISTORY_GAPS": True, "CORPORATE_ACTION_REVIEW": False,
                            "PRICE_BREAK_DETECTED": True, "NON_EQ_SERIES": False}


# ---------------------------------------------------------------- counts, run facts, banners

def test_counts_both_numbers_agreement_and_the_symbol_check(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    body = _get(client)[1]
    assert body["run"]["run_id"] == "r1" and body["evaluated"] == 7
    assert body["counts_rule"] == "recount equals stored run counts"
    assert body["counts"]["recount"]["status"]["VALID"] == 3 == body["counts"]["stored"]["status"]["VALID"]
    assert set(body["counts"]["agreement"]["status"].values()) == {"agree"}
    assert body["counts"]["symbols"] == {"requested": 7, "successful": 5, "failed": 2, "balanced": True}


def test_failed_symbols_note_for_flag_categories_only_except_non_eq(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    note = _get(client, "category=HISTORY_GAPS")[1]["failed_note"]
    assert "2 FAILED symbol(s) were not evaluated for HISTORY_GAPS" in note and "NON_EQ_SERIES" in note
    for category in ("NON_EQ_SERIES", "FAILED", "STALE", "INSUFFICIENT_HISTORY"):
        assert _get(client, f"category={category}")[1]["failed_note"] is None, category


def test_zero_rows_wording_never_says_zero_issues(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [("AAA", "VALID", []), ("BBB", "VALID", [])])
    res, body = _get(client, "category=STALE")
    assert body["rows"] == [] and body["total"] == 0 and body["total_pages"] == 0
    assert body["notice"] == "no symbols with STALE in run r1 (2 evaluated)"
    assert "0 issues" not in res.get_data(as_text=True)
    narrowed = _get(client, "category=FAILED&q=zzz")[1]["notice"]
    assert narrowed == "no symbols with FAILED match the current filters in run r1 (2 evaluated)"


def test_no_complete_run_and_missing_database(db, tmp_path, monkeypatch):
    res, body = _get(create_app(demo=False, db_path=db).test_client())
    assert res.status_code == 200 and body["run"] is None and body["message"] == "no COMPLETE scan run yet"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", tmp_path / "never_created.db")  # guard-allowed, absent
    assert _get(create_app(demo=False).test_client())[1]["status"] == "no_scans_yet"


def test_aborted_run_newer_than_the_latest_complete_is_excluded_and_bannered(db, client):
    _run(db, "r-prev", "2026-09-01T09:00:00", [("AAA", "STALE", [])])
    _run(db, "r-latest", "2026-09-02T09:00:00", [("AAA", "STALE", [])])
    _run(db, "r-aborted", "2026-09-03T09:00:00", [("ZZZ", "STALE", [])], end="ABORTED")
    body = _get(client, "category=STALE")[1]
    assert body["run"]["run_id"] == "r-latest" and body["previous_run"]["run_id"] == "r-prev"
    assert [r["symbol"] for r in body["rows"]] == ["AAA"]  # ZZZ lives only in the ABORTED run
    assert body["newer_run"]["run_id"] == "r-aborted" and "ABORTED (AUTH_FAILED)" in body["newer_run"]["reason"]


def test_aborted_and_smoke_runs_between_the_two_complete_runs_are_never_the_baseline(db, client):
    _run(db, "r-prev", "2026-09-01T09:00:00", [("AAA", "VALID", [])])
    _run(db, "r-abort", "2026-09-02T09:00:00", [("AAA", "STALE", [])], end="ABORTED")
    _run(db, "r-smoke", "2026-09-02T12:00:00", [("AAA", "FAILED", [])], smoke=["AAA"])
    _run(db, "r-latest", "2026-09-03T09:00:00", [("AAA", "STALE", [])])
    body = _get(client, "category=STALE")[1]
    assert body["previous_run"]["run_id"] == "r-prev"
    assert body["rows"][0]["changed_since_previous"]["changes"] == ["status VALID->STALE"]  # not vs ABORTED/smoke


def test_comparability_notes_when_universe_or_review_version_differs(db, client):
    _run(db, "r-prev", "2026-09-01T09:00:00", [("AAA", "STALE", [])], universe="uv-OLD", review="rv-OLD")
    _run(db, "r-latest", "2026-09-02T09:00:00", [("AAA", "STALE", [])], universe="uv-NEW", review="rv-NEW")
    notes = _get(client, "category=STALE")[1]["comparability_notes"]
    assert len(notes) == 2 and "universe_version differs" in notes[0] and "uv-NEW vs uv-OLD" in notes[0]
    assert "corporate_action_review_version differs" in notes[1]
    _run(db, "r-later", "2026-09-03T09:00:00", [("AAA", "STALE", [])], universe="uv-NEW", review="rv-NEW")
    assert _get(client, "category=STALE")[1]["comparability_notes"] == []


# ---------------------------------------------------------------- changed-since-previous marker

def _marker_runs(db):
    _run(db, "r-prev", "2026-09-01T09:00:00", [
        ("UNCH", "STALE", []), ("STAT", "VALID", []), ("FADD", "STALE", []), ("FREM", "STALE", ["history_gaps"]),
        ("FF", "VALID", ["history_gaps"]), ("GONE", "STALE", [])])
    _run(db, "r-latest", "2026-09-02T09:00:00", [
        ("UNCH", "STALE", []), ("STAT", "STALE", []), ("FADD", "STALE", ["history_gaps"]), ("FREM", "STALE", []),
        ("NEWSYM", "STALE", []), ("FF", "FAILED", [])])


def _markers(body):
    return {r["symbol"]: r["changed_since_previous"] for r in body["rows"]}


def test_marker_cases_unchanged_status_flag_added_removed_and_new(db, client):
    _marker_runs(db)
    m = _markers(_get(client, "category=STALE")[1])
    assert m["UNCH"] == {"state": "unchanged", "changes": [], "text": "unchanged"}
    assert m["STAT"]["state"] == "changed" and m["STAT"]["changes"] == ["status VALID->STALE"]
    assert m["FADD"]["changes"] == ["flag HISTORY_GAPS added"]
    assert m["FREM"]["changes"] == ["flag HISTORY_GAPS removed"]
    assert m["NEWSYM"] == {"state": "new", "changes": [], "text": "new in this run"}
    assert "GONE" not in m  # a symbol that left the run is not listed here


def test_new_symbol_is_never_reported_as_changed_and_changed_filter_excludes_it(db, client):
    _marker_runs(db)
    body = _get(client, "category=STALE&changed=1")[1]
    assert sorted(r["symbol"] for r in body["rows"]) == ["FADD", "FREM", "STAT"] and body["total"] == 3
    assert {r["changed_since_previous"]["state"] for r in body["rows"]} == {"changed"}


def test_failed_symbol_compares_status_and_non_eq_only_not_unevaluated_flags(db, client):
    _marker_runs(db)
    ff = _markers(_get(client, "category=FAILED")[1])["FF"]
    assert ff["changes"] == ["status VALID->FAILED"]  # the history_gaps flag it had before was never evaluated now


def test_no_previous_complete_run_marker_and_changed_filter(db, client):
    _run(db, "only", "2026-09-01T09:00:00", [("AAA", "STALE", [])])
    body = _get(client, "category=STALE")[1]
    assert body["previous_run"] is None
    assert body["rows"][0]["changed_since_previous"] == {
        "state": "no_previous_run", "changes": [], "text": "no previous COMPLETE run to compare"}
    changed = _get(client, "category=STALE&changed=1")[1]
    assert changed["rows"] == [] and changed["total"] == 0
    assert "needs a previous COMPLETE run" in changed["notice"]


def test_changed_filter_paginates_over_the_changed_set(db, client):
    _marker_runs(db)
    page2 = _get(client, "category=STALE&changed=1&page=2&page_size=2")[1]
    assert page2["total"] == 3 and page2["total_pages"] == 2 and [r["symbol"] for r in page2["rows"]] == ["STAT"]


# ---------------------------------------------------------------- filters, sort, pagination

def test_sector_q_sort_and_pagination(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [
        ("S1", "STALE", [], "Zeta Corp", "Energy"), ("S2", "STALE", [], "Alpha Corp", "IT"),
        ("S3", "STALE", [], "Mid Corp", "Auto")])
    sym = lambda q: [r["symbol"] for r in _get(client, "category=STALE&" + q)[1]["rows"]]
    assert sym("sort=symbol") == ["S1", "S2", "S3"] and sym("sort=symbol&dir=desc") == ["S3", "S2", "S1"]
    assert sym("sort=company_name") == ["S2", "S3", "S1"] and sym("sort=sector") == ["S3", "S1", "S2"]
    assert sym("sector=Auto") == ["S3"] and sym("q=alpha") == ["S2"]
    body = _get(client, "category=STALE&page=2&page_size=2")[1]
    assert [r["symbol"] for r in body["rows"]] == ["S3"] and body["total"] == 3 and body["total_pages"] == 2


def test_percent_and_underscore_in_q_are_literal_and_do_not_crash(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [
        ("P1", "STALE", [], "50% Foods"), ("P2", "STALE", [], "AB_CD Ltd"), ("P3", "STALE", [], "ABXCD Ltd"),
        ("P4", "STALE", [], "Plain Ltd")])
    sym = lambda q: [r["symbol"] for r in _get(client, "category=STALE&q=" + q)[1]["rows"]]
    assert sym("%25") == ["P1"]          # "%" matches only the name that contains a percent sign
    assert sym("_") == ["P2"]            # "_" matches only the name that contains an underscore
    assert sym("AB_CD") == ["P2"]        # not P3 (ABXCD): "_" is not a one-character wildcard
    assert sym("%255") == [] and sym("%5C") == [] and sym("%27") == []  # 5-with-percent, backslash, quote
    for nasty in ("%25%25", "__", "%5C%25", "%27%20OR%201%3D1%20--", "%00"):
        res = client.get("/api/equity/exceptions?category=STALE&q=" + nasty)
        assert res.status_code == 200, nasty


def test_default_get_candidates_behaviour_for_q_is_unchanged(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", [("P1", "STALE", [], "50% Foods"), ("P3", "STALE", [], "ABXCD Ltd")])
    ro = connection.get_read_only_connection(db)
    try:
        total, _ = queries.get_candidates(ro, "r1", 1, 25, "%")  # legacy: % is still a wildcard unless asked
    finally:
        ro.close()
    assert total == 2


# ---------------------------------------------------------------- invalid parameters, methods

@pytest.mark.parametrize("query", [
    "category=NOPE", "category=failed", "sort=status", "sort=rsi", "sort=;DROP", "dir=up", "dir=ASC2",
    "page=0", "page=-1", "page=abc", "page=1.5", "page_size=0", "page_size=201", "page_size=x", "changed=2",
    "changed=yes", "q=" + "x" * 101, "sector=" + "y" * 101,
])
def test_invalid_parameter_values_give_400_with_a_plain_message(db, client, query):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    res, body = _get(client, query)
    assert res.status_code == 400 and res.mimetype == "application/json"
    assert set(body) == {"error"} and "Traceback" not in body["error"] and len(body["error"]) < 200


def test_post_put_and_delete_are_405(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)("/api/equity/exceptions").status_code == 405, method


def test_a_run_id_parameter_is_not_accepted_the_latest_complete_run_is_always_used(db, client):
    _run(db, "r-old", "2026-09-01T09:00:00", [("OLD", "STALE", [])])
    _run(db, "r-latest", "2026-09-02T09:00:00", [("NEW", "STALE", [])])
    _run(db, "r-abort", "2026-09-03T09:00:00", [("ABT", "STALE", [])], end="ABORTED")
    body = _get(client, "category=STALE&run_id=r-abort")[1]
    assert body["run"]["run_id"] == "r-latest" and [r["symbol"] for r in body["rows"]] == ["NEW"]
    assert "run_id" not in body["params"]


# ---------------------------------------------------------------- safety

def test_response_has_no_env_or_token_text_and_no_score_rank_or_signal_keys(db, client):
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    text = client.get("/api/equity/exceptions?category=HISTORY_GAPS").get_data(as_text=True)
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
    walk(json.loads(text))
    assert not any(re.search(r"score|rank|signal|^buy$|^sell$|target|stop_?loss|confidence", k) for k in keys), keys
    assert json.loads(text)["scoring_status"] == "BLOCKED_B2"


def test_the_route_reads_through_a_read_only_connection_and_leaves_the_file_unchanged(db, monkeypatch):
    import sqlite3
    _run(db, "r1", "2026-09-01T09:00:00", CATEGORY_ROWS)
    seen = []
    real_build = exceptions.build

    def spying_build(conn, params):
        for statement in ("CREATE TABLE should_not_exist (x)", "UPDATE symbol_scan_results SET sector = 'X'",
                          "DELETE FROM scan_runs"):
            try:
                conn.execute(statement)
                seen.append("WRITE ALLOWED: " + statement)
            except sqlite3.OperationalError:
                seen.append("rejected")
        return real_build(conn, params)

    monkeypatch.setattr(exceptions, "build", spying_build)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    res = create_app(demo=False, db_path=db).test_client().get("/api/equity/exceptions?category=STALE&changed=1")
    assert res.status_code == 200 and seen == ["rejected"] * 3
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before

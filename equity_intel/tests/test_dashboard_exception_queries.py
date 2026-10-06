"""Phase 2 queries: get_previous_complete_run and get_exception_counts.

Every case builds its own runs in a tmp_path database (the demo seed's runs are identical, so they cannot
exercise comparisons). The seed's private insert helpers are reused so the rows match the real schema.
"""
import json
import sqlite3

import pytest

from dashboard import queries
from equity_intel.persistence import connection, db_path_guard
from scripts import dashboard_demo_seed as seed

NO_FLAGS = {"history_gaps": False, "corporate_action_review": False, "price_break_detected": False, "non_eq_series": False}


@pytest.fixture
def db(monkeypatch, tmp_path):
    # the DB guard only opens the canonical or demo path, so point both at tmp_path (never the real files)
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", tmp_path / "equity_intel_demo.db")
    conn = connection.get_connection(path)
    connection.initialize_schema(conn)
    conn.commit()
    conn.close()
    return path


def _add_run(db, run_id, started_at, *, end="COMPLETE", symbols=(), smoke=None, stored_status="auto",
             stored_flags="auto", successful=None, failed=None):
    """Build one run. `symbols` is [(symbol, status, {flag: bool})]; `end` is COMPLETE, ABORTED or RUNNING.

    COMPLETE runs store the true counts in status_counts_json / flag_counts_json (scanner-style upper-case
    flag keys) unless `stored_status` / `stored_flags` is a dict to store instead. Other runs are left
    unfinished, so raw text (including None = NULL or invalid JSON) can be stored there: the schema freezes
    finished runs, and a RUNNING row may carry any text. `successful` / `failed` override the true numbers.
    """
    extra = {} if smoke is None else {"symbols_filter_json": json.dumps(smoke)}
    if end != "COMPLETE":
        if stored_status != "auto":
            extra["status_counts_json"] = stored_status
        if stored_flags != "auto":
            extra["flag_counts_json"] = stored_flags
    conn = connection.get_connection(db)
    try:
        seed._insert_scan_run(conn, run_id, started_at, **extra)
        for symbol, status, flags in symbols:
            seed._insert_symbol_result(conn, run_id, symbol, symbol + " Co", "IT", status, None, {**NO_FLAGS, **flags})
        if end == "ABORTED":
            seed._abort_run(conn, run_id, started_at, "AUTH_FAILED", [])
        elif end == "COMPLETE":
            status_counts = {s: sum(1 for _, st, _ in symbols if st == s) for s in queries.STATUS_VALUES}
            flag_counts = {k.upper(): sum(1 for _, _, f in symbols if f.get(k)) for k in NO_FLAGS}
            seed._complete_run(
                conn, run_id, started_at, "2026-10-01",
                status_counts if stored_status == "auto" else stored_status,
                flag_counts if stored_flags == "auto" else stored_flags,
                requested=len(symbols),
                successful=successful if successful is not None else sum(1 for _, st, _ in symbols if st != "FAILED"),
                failed=failed if failed is not None else sum(1 for _, st, _ in symbols if st == "FAILED"))
        conn.commit()
    finally:
        conn.close()


def _ro(db):
    return connection.get_read_only_connection(db)


def _previous(db, latest_id):
    conn = _ro(db)
    try:
        return queries.get_previous_complete_run(conn, queries.get_run(conn, latest_id))
    finally:
        conn.close()


# ---------------------------------------------------------------- get_previous_complete_run

def test_previous_run_is_the_complete_full_run_just_before(db):
    _add_run(db, "r1", "2026-09-01T09:00:00")
    _add_run(db, "r2", "2026-09-02T09:00:00")
    _add_run(db, "r3", "2026-09-03T09:00:00")
    assert _previous(db, "r3")["run_id"] == "r2"
    assert _previous(db, "r2")["run_id"] == "r1"


def test_previous_run_skips_aborted_running_and_smoke_runs(db):
    _add_run(db, "r-base", "2026-09-01T09:00:00")
    _add_run(db, "r-abort", "2026-09-02T09:00:00", end="ABORTED")
    _add_run(db, "r-running", "2026-09-02T12:00:00", end="RUNNING")
    _add_run(db, "r-smoke", "2026-09-03T09:00:00", smoke=["AAA", "BBB"])
    _add_run(db, "r-latest", "2026-09-04T09:00:00")
    assert _previous(db, "r-latest")["run_id"] == "r-base"


def test_no_previous_run_returns_none(db):
    _add_run(db, "only", "2026-09-01T09:00:00")
    assert _previous(db, "only") is None
    _add_run(db, "r-abort", "2026-08-01T09:00:00", end="ABORTED")
    _add_run(db, "r-smoke", "2026-08-02T09:00:00", smoke=["AAA"])
    assert _previous(db, "only") is None
    assert queries.get_previous_complete_run(_ro(db), {"started_at": None}) is None


def test_equal_started_at_is_not_previous_and_ties_break_on_run_id_desc(db):
    _add_run(db, "r-a", "2026-09-01T09:00:00")
    _add_run(db, "r-b", "2026-09-01T09:00:00")  # same started_at as r-a
    _add_run(db, "r-c", "2026-09-02T09:00:00")
    assert _previous(db, "r-b") is None          # strict "<": an equal started_at is not previous
    assert _previous(db, "r-a") is None
    assert _previous(db, "r-c")["run_id"] == "r-b"  # two eligible runs tie on started_at: run_id DESC


def test_previous_run_never_returns_the_latest_run_itself(db):
    _add_run(db, "r1", "2026-09-01T09:00:00")
    _add_run(db, "r2", "2026-09-02T09:00:00")
    assert _previous(db, "r2")["run_id"] != "r2"


# ---------------------------------------------------------------- get_exception_counts

SYMBOLS = [
    ("AAA", "VALID", {}),
    ("BBB", "VALID", {"history_gaps": True}),
    ("CCC", "INSUFFICIENT_HISTORY", {"history_gaps": True, "price_break_detected": True}),
    ("DDD", "STALE", {"corporate_action_review": True}),
    ("EEE", "FAILED", {"non_eq_series": True}),
]


def _counts(db, run_id):
    conn = _ro(db)
    try:
        return queries.get_exception_counts(conn, run_id)
    finally:
        conn.close()


def test_recount_equals_stored_run_counts(db):
    _add_run(db, "r1", "2026-09-01T09:00:00", symbols=SYMBOLS)
    out = _counts(db, "r1")
    assert out["evaluated"] == 5
    assert out["recount"]["status"] == {"VALID": 2, "INSUFFICIENT_HISTORY": 1, "STALE": 1, "FAILED": 1}
    assert out["recount"]["flags"] == {"HISTORY_GAPS": 2, "CORPORATE_ACTION_REVIEW": 1,
                                       "PRICE_BREAK_DETECTED": 1, "NON_EQ_SERIES": 1}
    assert out["stored"]["status"] == out["recount"]["status"]
    assert out["stored"]["flags"] == out["recount"]["flags"]  # stored keys are upper case, as the scanner writes them
    assert set(out["agreement"]["status"].values()) == {"agree"} and set(out["agreement"]["flags"].values()) == {"agree"}


def test_lower_case_stored_flag_keys_are_matched(db):
    flags = {"history_gaps": 2, "corporate_action_review": 1, "price_break_detected": 1, "non_eq_series": 1}
    _add_run(db, "r1", "2026-09-01T09:00:00", symbols=SYMBOLS, stored_flags=flags)
    assert set(_counts(db, "r1")["agreement"]["flags"].values()) == {"agree"}


def test_deliberate_disagreement_is_reported_per_key(db):
    status = {"VALID": 3, "INSUFFICIENT_HISTORY": 1, "STALE": 1, "FAILED": 1}  # VALID stored as 3, really 2
    _add_run(db, "r1", "2026-09-01T09:00:00", symbols=SYMBOLS, stored_status=status)
    out = _counts(db, "r1")
    assert out["agreement"]["status"] == {"VALID": "disagree", "INSUFFICIENT_HISTORY": "agree",
                                          "STALE": "agree", "FAILED": "agree"}
    assert out["recount"]["status"]["VALID"] == 2 and out["stored"]["status"]["VALID"] == 3


@pytest.mark.parametrize("stored", [None, "not json {", "[1, 2]", '"text"', ""])
def test_null_or_invalid_stored_json_is_unavailable_never_zero(db, stored):
    _add_run(db, "r1", "2026-09-01T09:00:00", end="RUNNING", symbols=SYMBOLS, stored_status=stored, stored_flags=stored)
    out = _counts(db, "r1")
    assert out["stored"] == {"status": None, "flags": None}
    assert set(out["agreement"]["status"].values()) == {"unavailable"}
    assert set(out["agreement"]["flags"].values()) == {"unavailable"}
    assert out["recount"]["status"]["VALID"] == 2  # the recount is still reported


def test_missing_or_garbled_keys_in_stored_json_are_unavailable_not_zero(db):
    _add_run(db, "r1", "2026-09-01T09:00:00", end="RUNNING", symbols=SYMBOLS,
             stored_status=json.dumps({"VALID": 2, "STALE": "many", "FAILED": True}), stored_flags=json.dumps({}))
    out = _counts(db, "r1")
    assert out["stored"]["status"] == {"VALID": 2, "INSUFFICIENT_HISTORY": None, "STALE": None, "FAILED": None}
    assert out["agreement"]["status"] == {"VALID": "agree", "INSUFFICIENT_HISTORY": "unavailable",
                                          "STALE": "unavailable", "FAILED": "unavailable"}
    assert set(out["agreement"]["flags"].values()) == {"unavailable"}


def test_requested_successful_failed_and_balance_check(db):
    _add_run(db, "r1", "2026-09-01T09:00:00", symbols=SYMBOLS)
    assert _counts(db, "r1")["symbols"] == {"requested": 5, "successful": 4, "failed": 1, "balanced": True}
    _add_run(db, "r2", "2026-09-02T09:00:00", symbols=SYMBOLS, successful=4, failed=0)  # 4 + 0 != 5
    assert _counts(db, "r2")["symbols"] == {"requested": 5, "successful": 4, "failed": 0, "balanced": False}
    _add_run(db, "r3", "2026-09-03T09:00:00", end="RUNNING", symbols=SYMBOLS)  # counts still NULL
    assert _counts(db, "r3")["symbols"] == {"requested": None, "successful": None, "failed": None, "balanced": None}


def test_successful_below_requested_is_the_normal_case_when_a_symbol_failed(db):
    _add_run(db, "r1", "2026-09-01T09:00:00", symbols=SYMBOLS)
    symbols = _counts(db, "r1")["symbols"]
    assert symbols["successful"] < symbols["requested"] and symbols["balanced"] is True


def test_unknown_run_and_run_without_results(db):
    assert _counts(db, "nope") is None
    _add_run(db, "empty", "2026-09-01T09:00:00", end="RUNNING")
    out = _counts(db, "empty")
    assert out["evaluated"] == 0 and set(out["recount"]["status"].values()) == {0}  # evaluated 0, stated as such


def test_counts_are_for_the_requested_run_only(db):
    _add_run(db, "r1", "2026-09-01T09:00:00", symbols=SYMBOLS)
    _add_run(db, "r2", "2026-09-02T09:00:00", symbols=SYMBOLS[:2])
    assert _counts(db, "r1")["evaluated"] == 5 and _counts(db, "r2")["evaluated"] == 2


def test_flag_columns_come_only_from_the_whitelist():
    assert set(queries.FLAG_COLUMNS.values()) == {
        "history_gaps_flag", "corporate_action_review_flag", "price_break_detected_flag", "non_eq_series_flag"}


def test_read_only_connection_rejects_writes(db):
    _add_run(db, "r1", "2026-09-01T09:00:00", symbols=SYMBOLS)
    conn = _ro(db)
    try:
        queries.get_exception_counts(conn, "r1")
        queries.get_previous_complete_run(conn, queries.get_run(conn, "r1"))
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE symbol_scan_results SET sector = 'X'")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM scan_runs")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE should_not_exist (x)")
    finally:
        conn.close()

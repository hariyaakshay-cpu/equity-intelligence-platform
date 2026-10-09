"""Phase 4 queries: E4 scan detail, E4 status counts, ABORTED runs since a cutoff, benchmark last dates and the
ScanRun calendar's last date.

Every case builds its own tmp_path database (the DB guard paths are monkeypatched by the `db` fixture); nothing
reads or writes the real data/ files. These functions only return what is stored and whether it was readable;
the OK / WARN / UNKNOWN judgement is a later commit.
"""
import hashlib
import inspect
import json
import re
import sqlite3
from datetime import datetime, timedelta

import pytest

from dashboard import queries
from equity_intel.persistence import connection
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run, _ro

CUTOFF = datetime(2026, 10, 1, 12, 0, 0)          # naive IST, like every dashboard "now"
NEW_FUNCTIONS = (queries.get_latest_e4_scan_detail, queries.get_e4_status_counts, queries.get_aborted_runs_since,
                 queries.get_benchmark_last_dates, queries.get_calendar_last_date)


def _add_e4_scan(db, scan_id, started_at, *, status="COMPLETE", asof="2026-10-01", acq="acq-1", completed="2026-10-01T10:00:00+00:00",
                 quality=(), features=0, calendar="PROVISIONAL"):
    """One E4 scan with a quality row per entry of `quality` (its status) and `features` feature rows."""
    conn = connection.connect(db)          # also creates the E4 / acquisition tables
    try:
        conn.execute(
            "INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,completed_at,status,asof_date,calendar_status,"
            "indicator_config_json) VALUES(?,?,?,?,?,?,?,?)", (scan_id, acq, started_at, completed, status, asof, calendar, "{}"))
        for i, quality_status in enumerate(quality):
            conn.execute(
                "INSERT INTO e4_data_quality_results(scan_id,symbol,status,reason,n_bars,w52_complete,break_date,break_ratio,volume_usable) "
                "VALUES(?,?,?,NULL,252,1,NULL,NULL,1)", (scan_id, f"S{i:03d}", quality_status))
        for i in range(features):
            conn.execute("INSERT INTO e4_feature_sets(scan_id,symbol,last_date) VALUES(?,?,?)", (scan_id, f"S{i:03d}", asof))
        conn.commit()
    finally:
        conn.close()


def _add_benchmark(db, run_id, key, dates):
    conn = connection.connect(db)
    try:
        for d in dates:
            conn.execute("INSERT INTO acquired_benchmark VALUES(?,?,?,?,?,?)", (run_id, key, d, 1000.0, "test", "2026-10-01T10:00:00+05:30"))
        conn.commit()
    finally:
        conn.close()


def _set_calendar(db, run_id, raw):
    """A RUNNING run may carry any text in calendar_dates_json (finished runs are frozen by the schema)."""
    conn = connection.get_connection(db)
    try:
        conn.execute("UPDATE scan_runs SET calendar_dates_json = ? WHERE run_id = ?", (raw, run_id))
        conn.commit()
    finally:
        conn.close()


def _call(db, function, *args):
    conn = _ro(db)
    try:
        return function(conn, *args)
    finally:
        conn.close()


# ---------------------------------------------------------------- the latest E4 scan, with timestamps

def test_latest_e4_detail_is_the_scan_get_latest_e4_scan_picks_with_timestamps_and_acquisition_id(db):
    _add_e4_scan(db, "e4-old", "2026-09-20T10:00:00+00:00", asof="2026-09-18", acq="acq-old", quality=["VALID"], features=1)
    _add_e4_scan(db, "e4-new", "2026-10-01T10:00:00+00:00", asof="2026-10-01", acq="acq-new", completed="2026-10-01T10:05:00+00:00", features=1)
    _add_e4_scan(db, "e4-failed", "2026-10-02T10:00:00+00:00", status="FAILED", asof=None, acq="acq-f", features=1)
    _add_e4_scan(db, "e4-running", "2026-10-03T10:00:00+00:00", status="RUNNING", asof=None, acq="acq-r", features=1)
    detail = _call(db, queries.get_latest_e4_scan_detail)
    assert detail["scan_id"] == _call(db, queries.get_latest_e4_scan)["scan_id"] == "e4-new"      # FAILED / RUNNING are never "latest"
    assert (detail["acquisition_run_id"], detail["asof_date"], detail["calendar_status"]) == ("acq-new", "2026-10-01", "PROVISIONAL")
    assert detail["started_at"] == "2026-10-01T10:00:00+00:00" and detail["completed_at"] == "2026-10-01T10:05:00+00:00"
    assert set(detail) == {"scan_id", "acquisition_run_id", "started_at", "completed_at", "asof_date", "asof_date_raw",
                           "calendar_status", "started_at_ist", "completed_at_ist"}


def test_utc_aware_and_naive_timestamps_both_become_naive_ist(db):
    _add_e4_scan(db, "e4-utc", "2026-10-01T12:30:00+00:00", completed="2026-10-01T20:00:00+00:00")
    detail = _call(db, queries.get_latest_e4_scan_detail)
    assert detail["started_at_ist"] == "2026-10-01T18:00:00"          # UTC + 5:30
    assert detail["completed_at_ist"] == "2026-10-02T01:30:00"        # crosses IST midnight


@pytest.mark.parametrize("stored, expected", [
    ("2026-10-01T18:00:00+05:30", "2026-10-01T18:00:00"),             # already IST-aware: unchanged wall clock
    ("2026-10-01T18:00:00", "2026-10-01T18:00:00"),                   # naive: taken as IST, as scan_runs are
    ("2026-10-01T18:00:00.123456+00:00", "2026-10-01T23:30:00"),      # microseconds, UTC
    ("2026-10-01 18:00:00", "2026-10-01T18:00:00"),                   # space separator
])
def test_timestamp_forms_are_normalised_to_naive_ist(db, stored, expected):
    _add_e4_scan(db, "e4-1", stored, completed=stored)
    detail = _call(db, queries.get_latest_e4_scan_detail)
    assert detail["started_at_ist"] == expected and detail["completed_at_ist"] == expected


def test_null_and_unparseable_e4_values_are_missing_not_defaulted(db):
    _add_e4_scan(db, "e4-null", "2026-10-01T10:00:00+00:00", completed=None, asof=None)
    detail = _call(db, queries.get_latest_e4_scan_detail)
    assert (detail["completed_at"], detail["completed_at_ist"], detail["asof_date"], detail["asof_date_raw"]) == (None, None, None, None)
    for bad in ("garbage", "", "2026-13-45T99:99:99", "not a time"):
        _add_e4_scan(db, f"e4-bad-{len(bad)}", "2026-10-02T10:00:00+00:00", completed=bad)
    detail = _call(db, queries.get_latest_e4_scan_detail)
    assert detail["scan_id"].startswith("e4-bad") and detail["completed_at_ist"] is None and detail["started_at_ist"] == "2026-10-02T15:30:00"


@pytest.mark.parametrize("stored", ["2026-13-45", "20261001", "2026-10-1", "October 1", "", "2026-10-01T10:00:00"])
def test_an_invalid_asof_date_is_none_but_the_raw_value_is_kept(db, stored):
    _add_e4_scan(db, "e4-1", "2026-10-01T10:00:00+00:00", asof=stored)
    detail = _call(db, queries.get_latest_e4_scan_detail)
    assert detail["asof_date"] is None and detail["asof_date_raw"] == stored


def test_no_e4_tables_or_no_complete_e4_scan_is_none(db):
    assert _call(db, queries.get_latest_e4_scan_detail) is None                      # the E4 tables do not exist yet
    _add_e4_scan(db, "e4-running", "2026-10-01T10:00:00+00:00", status="RUNNING", asof=None)
    assert _call(db, queries.get_latest_e4_scan_detail) is None and _call(db, queries.get_latest_e4_scan) is None


# ---------------------------------------------------------------- the E4 layer's own status counts

def test_status_counts_are_read_from_the_data_with_each_layers_own_total(db):
    _make_run(db, "r1", "2026-10-01T09:00:00", [(f"A{i}", "VALID", []) for i in range(5)] + [("B", "INSUFFICIENT_HISTORY", [])])   # ScanRun: 6 symbols
    _add_e4_scan(db, "e4-a", "2026-10-01T10:00:00+00:00", quality=["VALID"] * 7 + ["INSUFFICIENT_HISTORY"] * 3 + ["WEIRD_NEW_STATUS"], features=9)
    _add_e4_scan(db, "e4-b", "2026-09-01T10:00:00+00:00", quality=["VALID"], features=1)
    a = _call(db, queries.get_e4_status_counts, "e4-a")
    assert a == {"scan_id": "e4-a", "total": 11, "counts": {"INSUFFICIENT_HISTORY": 3, "VALID": 7, "WEIRD_NEW_STATUS": 1}, "feature_sets": 9}
    assert list(a["counts"]) == sorted(a["counts"])                                  # ordered by name; no assumed or zero-filled status
    assert _call(db, queries.get_e4_status_counts, "e4-b")["counts"] == {"VALID": 1}
    scan_run = _call(db, queries.get_exception_counts, "r1")
    assert scan_run["evaluated"] == 6 and a["total"] == 11                           # two layers, two denominators, never one total


def test_the_real_situation_shape_two_layers_with_different_counts(db):
    """486 / 14 in the ScanRun and 484 / 16 in E4 (the user's observation): both come back as stored, side by side."""
    _make_run(db, "r1", "2026-10-02T09:00:00", [(f"V{i:03d}", "VALID", []) for i in range(486)] + [(f"I{i:03d}", "INSUFFICIENT_HISTORY", []) for i in range(14)])
    _add_e4_scan(db, "e4-1", "2026-10-02T10:00:00+00:00", asof="2026-10-01", quality=["VALID"] * 484 + ["INSUFFICIENT_HISTORY"] * 16, features=484)
    e4 = _call(db, queries.get_e4_status_counts, "e4-1")
    scan_run = _call(db, queries.get_exception_counts, "r1")
    assert (e4["counts"], e4["total"]) == ({"INSUFFICIENT_HISTORY": 16, "VALID": 484}, 500)
    assert (scan_run["recount"]["status"]["VALID"], scan_run["recount"]["status"]["INSUFFICIENT_HISTORY"], scan_run["evaluated"]) == (486, 14, 500)
    assert _call(db, queries.get_latest_e4_scan_detail)["asof_date"] == "2026-10-01"


def test_an_e4_scan_with_no_quality_rows_has_total_zero_and_unknown_scan_ids_are_empty(db):
    _add_e4_scan(db, "e4-empty", "2026-10-01T10:00:00+00:00", features=0)
    assert _call(db, queries.get_e4_status_counts, "e4-empty") == {"scan_id": "e4-empty", "total": 0, "counts": {}, "feature_sets": 0}
    assert _call(db, queries.get_e4_status_counts, "nope")["total"] == 0


def test_status_counts_is_none_without_the_quality_table_and_is_parameterized(db):
    assert _call(db, queries.get_e4_status_counts, "e4-1") is None
    _add_e4_scan(db, "e4-1", "2026-10-01T10:00:00+00:00", quality=["VALID"])
    assert _call(db, queries.get_e4_status_counts, "e4-1' OR '1'='1")["total"] == 0


# ---------------------------------------------------------------- ABORTED runs since a cutoff

def test_the_seven_day_boundary_is_inclusive_to_the_second(db):
    _make_run(db, "r-before", "2026-10-01T11:59:59", end="ABORTED")
    _make_run(db, "r-exact", "2026-10-01T12:00:00", end="ABORTED")
    _make_run(db, "r-after", "2026-10-01T12:00:01", end="ABORTED")
    out = _call(db, queries.get_aborted_runs_since, CUTOFF)
    assert [r["run_id"] for r in out["full"]["runs"]] == ["r-after", "r-exact"] and out["full"]["count"] == 2
    assert out["aborted_total"] == 3 and out["cutoff"] == "2026-10-01T12:00:00" and out["unparseable"] == []
    seven_days_ago = datetime(2026, 10, 8, 9, 30, 0) - timedelta(days=7)               # 2026-10-01 09:30: all three are inside
    assert _call(db, queries.get_aborted_runs_since, seven_days_ago)["full"]["count"] == 3
    assert _call(db, queries.get_aborted_runs_since, datetime(2026, 10, 1, 12, 0, 1))["full"]["count"] == 1


def test_only_aborted_runs_are_counted_never_complete_or_running(db):
    _make_run(db, "r-complete", "2026-10-02T09:00:00", [("AAA", "VALID", [])])
    _make_run(db, "r-running", "2026-10-02T10:00:00", end="RUNNING")
    _make_run(db, "r-abort", "2026-10-02T11:00:00", end="ABORTED", abort_reason="AUTH_FAILED")
    out = _call(db, queries.get_aborted_runs_since, CUTOFF)
    assert out["full"] == {"count": 1, "runs": [{"run_id": "r-abort", "started_at": "2026-10-02T11:00:00", "abort_reason": "AUTH_FAILED"}], "more": 0}
    assert out["smoke"]["count"] == 0 and out["aborted_total"] == 1
    assert _call(db, queries.get_latest_complete_run)["run_id"] == "r-complete"     # an ABORTED run is not "latest" anything


def test_smoke_and_full_aborted_runs_are_separated_and_never_added_together(db):
    _make_run(db, "r-full-1", "2026-10-02T09:00:00", end="ABORTED")
    _make_run(db, "r-full-2", "2026-10-03T09:00:00", end="ABORTED", abort_reason="CALENDAR_INVALID")
    _make_run(db, "r-smoke", "2026-10-04T09:00:00", [("AAA", "VALID", [])], end="ABORTED", smoke=json.dumps(["AAA"]))
    out = _call(db, queries.get_aborted_runs_since, CUTOFF)
    assert (out["full"]["count"], out["smoke"]["count"], out["aborted_total"]) == (2, 1, 3)
    assert [r["run_id"] for r in out["full"]["runs"]] == ["r-full-2", "r-full-1"] and [r["run_id"] for r in out["smoke"]["runs"]] == ["r-smoke"]
    assert out["full"]["runs"][0]["abort_reason"] == "CALENDAR_INVALID"
    assert "total" not in out and "count" not in out                                 # there is no combined figure


def test_an_unparseable_started_at_is_listed_not_counted_and_not_dropped(db):
    _make_run(db, "r-bad", "garbage", end="ABORTED")
    _make_run(db, "r-ok", "2026-10-02T09:00:00", end="ABORTED")
    _make_run(db, "r-old", "2026-01-01T09:00:00", end="ABORTED")
    out = _call(db, queries.get_aborted_runs_since, CUTOFF)
    assert out["unparseable"] == ["r-bad"] and out["full"]["count"] == 1 and out["aborted_total"] == 3


def test_a_utc_aware_started_at_is_compared_in_ist(db):
    _make_run(db, "r-utc-inside", "2026-10-01T06:30:00+00:00", end="ABORTED")          # 12:00 IST: exactly the cutoff
    _make_run(db, "r-utc-outside", "2026-10-01T06:29:59+00:00", end="ABORTED")         # 11:59:59 IST
    out = _call(db, queries.get_aborted_runs_since, CUTOFF)
    assert [r["run_id"] for r in out["full"]["runs"]] == ["r-utc-inside"] and out["full"]["runs"][0]["started_at"] == "2026-10-01T12:00:00"


def test_the_aborted_list_is_capped_but_the_count_is_true(db):
    for i in range(queries.ABORTED_LIST_LIMIT + 2):
        _make_run(db, f"r-{i:03d}", f"2026-10-02T09:{i // 60:02d}:{i % 60:02d}", end="ABORTED")
    full = _call(db, queries.get_aborted_runs_since, CUTOFF)["full"]
    assert full["count"] == 52 and len(full["runs"]) == 50 and full["more"] == 2
    assert full["runs"][0]["run_id"] == "r-051"                                        # newest first


def test_no_aborted_runs_is_zero_with_empty_lists(db):
    _make_run(db, "r1", "2026-10-02T09:00:00", [("AAA", "VALID", [])])
    out = _call(db, queries.get_aborted_runs_since, CUTOFF)
    assert out["full"] == {"count": 0, "runs": [], "more": 0} and out["smoke"] == {"count": 0, "runs": [], "more": 0}
    assert out["aborted_total"] == 0 and out["unparseable"] == []


# ---------------------------------------------------------------- the index candles of each layer

def test_benchmark_last_dates_return_each_key_as_stored_the_demo_key_and_the_real_key(db):
    _add_benchmark(db, "acq-real", "NSE_INDEX|Nifty 500", ["2026-09-30", "2026-10-01", "2026-09-29"])
    _add_benchmark(db, "acq-demo", "DEMO_INDEX", ["2026-09-25", "2026-09-24"])
    assert _call(db, queries.get_benchmark_last_dates, "acq-real") == [{"benchmark_key": "NSE_INDEX|Nifty 500", "last_date": "2026-10-01", "sessions": 3}]
    assert _call(db, queries.get_benchmark_last_dates, "acq-demo") == [{"benchmark_key": "DEMO_INDEX", "last_date": "2026-09-25", "sessions": 2}]


def test_several_benchmark_keys_in_one_run_are_all_reported_ordered_by_key(db):
    _add_benchmark(db, "acq-1", "NSE_INDEX|Nifty 500", ["2026-10-01"])
    _add_benchmark(db, "acq-1", "NSE_INDEX|Nifty 50", ["2026-09-30"])
    out = _call(db, queries.get_benchmark_last_dates, "acq-1")
    assert [(e["benchmark_key"], e["last_date"]) for e in out] == [("NSE_INDEX|Nifty 50", "2026-09-30"), ("NSE_INDEX|Nifty 500", "2026-10-01")]


def test_benchmark_edge_cases_unparseable_date_no_rows_and_no_table(db):
    assert _call(db, queries.get_benchmark_last_dates, "acq-1") is None               # table not created yet
    _add_benchmark(db, "acq-bad", "K", ["not-a-date"])
    _add_benchmark(db, "acq-other", "K", ["2026-10-01"])
    assert _call(db, queries.get_benchmark_last_dates, "acq-bad") == [{"benchmark_key": "K", "last_date": None, "sessions": 1}]
    assert _call(db, queries.get_benchmark_last_dates, "acq-none") == []
    assert _call(db, queries.get_benchmark_last_dates, "acq-1' OR '1'='1") == []


def test_calendar_last_date_is_the_maximum_of_the_stored_session_list(db):
    _make_run(db, "r1", "2026-10-02T09:00:00", end="RUNNING")
    _set_calendar(db, "r1", json.dumps(["2026-09-30", "2026-10-01", "2026-09-29", "2026-10-01"]))
    assert _call(db, queries.get_calendar_last_date, "r1") == {"state": "ok", "last_date": "2026-10-01", "sessions": 3}


@pytest.mark.parametrize("raw, state", [
    (None, "missing"), ("", "missing"), ("[]", "missing"),
    ("not json", "unparseable"), ('{"a": 1}', "unparseable"), ('"2026-10-01"', "unparseable"), ("42", "unparseable"),
    ('["2026-10-01", "bad"]', "unparseable"), ('["2026-10-01", 20261001]', "unparseable"), ('["2026-10-01", null]', "unparseable"),
    ('["2026-13-01"]', "unparseable"),
])
def test_calendar_last_date_missing_and_unparseable_forms(db, raw, state):
    _make_run(db, "r1", "2026-10-02T09:00:00", end="RUNNING")
    _set_calendar(db, "r1", raw)
    assert _call(db, queries.get_calendar_last_date, "r1") == {"state": state, "last_date": None, "sessions": 0}


def test_calendar_last_date_of_an_unknown_run_is_none(db):
    assert _call(db, queries.get_calendar_last_date, "nope") is None


# ---------------------------------------------------------------- read-only, parameterized, nothing else changed

def test_the_new_queries_run_on_a_read_only_connection_and_leave_the_file_unchanged(db):
    _make_run(db, "r1", "2026-10-02T09:00:00", end="ABORTED")
    _add_e4_scan(db, "e4-1", "2026-10-01T10:00:00+00:00", quality=["VALID"], features=1)
    _add_benchmark(db, "acq-1", "DEMO_INDEX", ["2026-10-01"])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    conn = _ro(db)
    try:
        queries.get_latest_e4_scan_detail(conn)
        queries.get_e4_status_counts(conn, "e4-1")
        queries.get_aborted_runs_since(conn, CUTOFF)
        queries.get_benchmark_last_dates(conn, "acq-1")
        queries.get_calendar_last_date(conn, "r1")
        for statement in ("CREATE TABLE should_not_exist (x)", "UPDATE scan_runs SET status = 'COMPLETE'",
                          "DELETE FROM e4_scan_runs", "DROP TABLE acquired_benchmark", "INSERT INTO acquired_benchmark VALUES('a','b','c',1,'d','e')"):
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(statement)
    finally:
        conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_the_new_query_source_has_no_write_statement_and_no_interpolated_input():
    for function in NEW_FUNCTIONS:
        source = inspect.getsource(function)
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|REPLACE)\b", source), function.__name__
        assert "f\"SELECT" not in source and "f'SELECT" not in source and ".format(" not in source and "% (" not in source, function.__name__
        assert "sqlite3" not in source


def test_the_new_functions_do_not_judge_or_score(db):
    _add_e4_scan(db, "e4-1", "2026-10-01T10:00:00+00:00", quality=["VALID"], features=1)
    _make_run(db, "r1", "2026-10-02T09:00:00", end="ABORTED")
    blob = json.dumps([_call(db, queries.get_latest_e4_scan_detail), _call(db, queries.get_e4_status_counts, "e4-1"),
                       _call(db, queries.get_aborted_runs_since, CUTOFF)]).lower()
    assert not re.search(r"\b(ok|warn|warning|score|rank|signal|stale_state)\b", blob)


# ---------------------------------------------------------------- RUNNING runs and the cross-layer status differences (commit 2)

def test_running_runs_are_listed_newest_first_with_a_smoke_flag_and_unparseable_starts_kept(db):
    _make_run(db, "r-old", "2026-10-01T09:00:00", end="RUNNING")
    _make_run(db, "r-smoke", "2026-10-02T09:00:00", [("AAA", "VALID", [])], end="RUNNING", smoke=json.dumps(["AAA"]))
    _make_run(db, "r-bad", "garbage", end="RUNNING")
    _make_run(db, "r-utc", "2026-10-01T06:30:00+00:00", end="RUNNING")
    _make_run(db, "r-abort", "2026-10-03T09:00:00", end="ABORTED")
    _make_run(db, "r-done", "2026-10-03T10:00:00", [("AAA", "VALID", [])])
    runs = {r["run_id"]: r for r in _call(db, queries.get_running_runs)}
    assert set(runs) == {"r-old", "r-smoke", "r-bad", "r-utc"}                        # ABORTED and COMPLETE are never RUNNING
    ordered = [r["run_id"] for r in _call(db, queries.get_running_runs) if r["run_id"] != "r-bad"]    # text order; an unparseable value sorts wherever its text does
    assert ordered[0] == "r-smoke" and ordered[-1] == "r-utc"
    assert runs["r-smoke"]["smoke"] is True and runs["r-old"]["smoke"] is False
    assert runs["r-bad"]["started_at_ist"] is None and runs["r-bad"]["started_at"] == "garbage"
    assert runs["r-utc"]["started_at_ist"] == "2026-10-01T12:00:00"


def _layer_pair(db, scanrun, e4):
    """A COMPLETE ScanRun with {symbol: status} and an E4 scan with {symbol: status}."""
    from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run as make
    make(db, "r1", "2026-10-02T09:00:00", [(s, status, []) for s, status in scanrun.items()])
    conn = connection.connect(db)
    try:
        conn.execute("INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,status,asof_date,calendar_status,indicator_config_json) "
                     "VALUES('e4-1','acq-1','2026-10-02T10:00:00+00:00','COMPLETE','2026-10-01','PROVISIONAL','{}')")
        for symbol, status in e4.items():
            conn.execute("INSERT INTO e4_data_quality_results(scan_id,symbol,status,reason,n_bars,w52_complete,break_date,break_ratio,volume_usable) "
                         "VALUES('e4-1',?,?,?,252,1,NULL,NULL,1)", (symbol, status, "40 bars; 252 required" if status != "VALID" else None))
        conn.commit()
    finally:
        conn.close()


def test_layer_disagreements_list_symbols_whose_status_differs_and_count_one_sided_ones_separately(db):
    _layer_pair(db, {"AAA": "VALID", "BBB": "VALID", "CCC": "INSUFFICIENT_HISTORY", "ONLYSCAN": "VALID", "FAILEDONE": "FAILED"},
                {"AAA": "VALID", "BBB": "INSUFFICIENT_HISTORY", "CCC": "INSUFFICIENT_HISTORY", "ONLYE4": "VALID"})
    out = _call(db, queries.get_layer_status_disagreements, "r1", "e4-1")
    assert (out["in_both"], out["different"], out["only_in_scanrun"], out["only_in_e4"], out["more"]) == (3, 1, 2, 1, 0)
    (row,) = out["rows"]
    assert (row["symbol"], row["scanrun_status"], row["e4_status"], row["e4_reason"]) == ("BBB", "VALID", "INSUFFICIENT_HISTORY", "40 bars; 252 required")
    assert "FAILEDONE" not in json.dumps(out) and "ONLYE4" not in json.dumps(out)    # one-sided symbols are counted, not listed as differences


def test_layer_disagreements_are_capped_with_a_true_count_ordered_by_symbol_and_parameterized(db):
    symbols = [f"S{i:03d}" for i in range(7)]
    _layer_pair(db, {s: "VALID" for s in symbols}, {s: "INSUFFICIENT_HISTORY" for s in symbols})
    out = _call(db, queries.get_layer_status_disagreements, "r1", "e4-1", 3)
    assert out["different"] == 7 and [r["symbol"] for r in out["rows"]] == ["S000", "S001", "S002"] and out["more"] == 4
    empty = _call(db, queries.get_layer_status_disagreements, "r1' OR '1'='1", "e4-1")
    assert (empty["in_both"], empty["different"], empty["rows"]) == (0, 0, [])


def test_layer_disagreements_is_none_without_the_e4_table(db):
    assert _call(db, queries.get_layer_status_disagreements, "r1", "e4-1") is None

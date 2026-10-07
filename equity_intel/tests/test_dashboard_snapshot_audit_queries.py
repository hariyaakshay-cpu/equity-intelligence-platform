"""Phase 3 queries: run eligibility, symbol-set diff and "bars whose stored hash differs" between two runs.

Every case builds its own runs in a tmp_path database through the scanner's own snapshot writer. Nothing here
reads or writes the real data/ files (the DB guard paths are monkeypatched by the `db` fixture).
"""
import hashlib
import inspect
import json
import re
import sqlite3
import statistics
import time
from datetime import date, timedelta

import pytest

from dashboard import queries
from equity_intel.persistence import connection, db_path_guard
from equity_intel.scanner.snapshots import compute_content_hash, write_snapshot
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from scripts import dashboard_demo_seed as seed

NO_FLAGS = {"history_gaps": False, "corporate_action_review": False, "price_break_detected": False, "non_eq_series": False}


def _ro(db):
    return connection.get_read_only_connection(db)


def _make_run(db, run_id, started_at, symbols=(), *, end="COMPLETE", smoke=None, requested="auto", abort_reason="AUTH_FAILED"):
    """symbols: (symbol, status, bars) or (symbol, status, bars, company_name, sector); bars: [(date, close[, volume[, source]])].
    Bars go through the scanner's own write_snapshot, so stored hashes are the real ones."""
    extra = {} if smoke is None else {"symbols_filter_json": smoke}
    conn = connection.get_connection(db)
    try:
        seed._insert_scan_run(conn, run_id, started_at, **extra)
        for entry in symbols:
            symbol, status, bars, *rest = entry
            name = rest[0] if rest else symbol + " Co"
            sector = rest[1] if len(rest) > 1 else "IT"
            seed._insert_symbol_result(conn, run_id, symbol, name, sector, status, None, NO_FLAGS)
            for bar in bars:
                trading_date, close, *more = bar
                volume = more[0] if more else 1000
                source = more[1] if len(more) > 1 else "upstox"
                write_snapshot(conn, scan_run_id=run_id, symbol=symbol, trading_date=trading_date, source=source,
                               fetched_at_ist=started_at + "+05:30", open_=close - 1, high=close + 2, low=close - 2,
                               close=close, volume=volume, candle_validation_status="VALID")
        if end == "ABORTED":
            seed._abort_run(conn, run_id, started_at, abort_reason, [])
        elif end == "COMPLETE":
            failed = sum(1 for s in symbols if s[1] == "FAILED")
            status_counts = {st: sum(1 for s in symbols if s[1] == st) for st in queries.STATUS_VALUES}
            seed._complete_run(conn, run_id, started_at, "2026-10-01", status_counts, {k: 0 for k in NO_FLAGS},
                               requested=len(symbols) if requested == "auto" else requested,
                               successful=len(symbols) - failed, failed=failed)
        conn.commit()
    finally:
        conn.close()


def _d(n):
    return (date(2026, 1, 1) + timedelta(days=n)).isoformat()


# ---------------------------------------------------------------- eligible and ineligible runs

def test_eligible_runs_are_complete_full_runs_newest_first(db):
    _make_run(db, "r1", "2026-09-01T09:00:00")
    _make_run(db, "r2", "2026-09-02T09:00:00")
    _make_run(db, "r-abort", "2026-09-03T09:00:00", end="ABORTED")
    _make_run(db, "r-running", "2026-09-03T12:00:00", end="RUNNING")
    _make_run(db, "r-smoke", "2026-09-04T09:00:00", [("AAA", "VALID", [])], smoke=json.dumps(["AAA"]))
    _make_run(db, "r3", "2026-09-05T09:00:00")
    conn = _ro(db)
    try:
        out = queries.get_eligible_runs(conn)
        assert [r["run_id"] for r in out["runs"]] == ["r3", "r2", "r1"] and out["total"] == 3 and out["more"] == 0
        assert all(r["status"] == "COMPLETE" for r in out["runs"])
        assert "symbols_filter_json" not in out["runs"][0]
        limited = queries.get_eligible_runs(conn, limit=2)
        assert [r["run_id"] for r in limited["runs"]] == ["r3", "r2"] and limited["total"] == 3 and limited["more"] == 1
    finally:
        conn.close()


def test_aborted_running_and_smoke_runs_are_never_eligible_and_always_listed_as_ineligible(db):
    _make_run(db, "r1", "2026-09-01T09:00:00")
    _make_run(db, "r-abort", "2026-09-02T09:00:00", end="ABORTED")
    _make_run(db, "r-running", "2026-09-03T09:00:00", end="RUNNING")
    _make_run(db, "r-smoke", "2026-09-04T09:00:00", [("AAA", "VALID", []), ("BBB", "VALID", [])], smoke=json.dumps(["AAA", "BBB"]))
    conn = _ro(db)
    try:
        eligible = {r["run_id"] for r in queries.get_eligible_runs(conn)["runs"]}
        ineligible = queries.get_ineligible_runs(conn)
        assert eligible == {"r1"}
        assert {r["run_id"] for r in ineligible["runs"]} == {"r-abort", "r-running", "r-smoke"}
        assert eligible.isdisjoint({r["run_id"] for r in ineligible["runs"]})
        by_id = {r["run_id"]: r for r in ineligible["runs"]}
        assert (by_id["r-abort"]["kind"], by_id["r-abort"]["reason"]) == ("ABORTED", "ABORTED (AUTH_FAILED)")
        assert (by_id["r-running"]["kind"], by_id["r-running"]["reason"]) == ("RUNNING", "RUNNING (not finished)")
        assert (by_id["r-smoke"]["kind"], by_id["r-smoke"]["reason"]) == ("SMOKE", "smoke run (--symbols, 2 symbols)")
        # newest first
        assert [r["run_id"] for r in ineligible["runs"]] == ["r-smoke", "r-running", "r-abort"]
    finally:
        conn.close()


def test_ineligible_runs_show_requested_and_stored_counts_with_null_as_none(db):
    _make_run(db, "r-abort", "2026-09-02T09:00:00", end="ABORTED")                       # nothing recorded
    _make_run(db, "r-smoke", "2026-09-04T09:00:00", [("AAA", "VALID", [])], smoke=json.dumps(["AAA"]))
    conn = _ro(db)
    try:
        by_id = {r["run_id"]: r for r in queries.get_ineligible_runs(conn)["runs"]}
        assert by_id["r-abort"]["requested_symbols"] is None and by_id["r-abort"]["stored_symbols"] == 0   # unavailable / 0 rows
        assert by_id["r-abort"]["successful_symbols"] is None and by_id["r-abort"]["failed_symbols"] is None
        assert by_id["r-smoke"]["requested_symbols"] == 1 and by_id["r-smoke"]["stored_symbols"] == 1
    finally:
        conn.close()


def test_ineligible_list_is_the_newest_twenty_plus_a_count_of_the_rest(db):
    for i in range(23):  # 23 aborted runs, run 22 the newest
        _make_run(db, f"r-abort-{i:02d}", f"2026-08-{i + 1:02d}T09:00:00", end="ABORTED")
    _make_run(db, "r-ok", "2026-09-01T09:00:00")
    conn = _ro(db)
    try:
        out = queries.get_ineligible_runs(conn)
        assert out["total"] == 23 and len(out["runs"]) == 20 == queries.INELIGIBLE_RUN_LIST_LIMIT and out["more"] == 3
        assert out["runs"][0]["run_id"] == "r-abort-22" and out["runs"][-1]["run_id"] == "r-abort-03"
        assert "r-ok" not in {r["run_id"] for r in out["runs"]}
        assert queries.get_ineligible_runs(conn, limit=100)["more"] == 0
    finally:
        conn.close()


def test_a_smoke_run_with_an_unreadable_symbol_list_is_still_ineligible(db):
    _make_run(db, "r-smoke", "2026-09-04T09:00:00", [("AAA", "VALID", [])], smoke="not json")
    conn = _ro(db)
    try:
        assert queries.get_eligible_runs(conn)["total"] == 0
        run = queries.get_ineligible_runs(conn)["runs"][0]
        assert run["kind"] == "SMOKE" and "unreadable" in run["reason"]
    finally:
        conn.close()


# ---------------------------------------------------------------- symbol set diff

def _two_runs_with_added_and_removed(db):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [
        ("BOTH1", "VALID", []), ("BOTH2", "STALE", []), ("GONE1", "VALID", [], "Gone One Ltd", "Auto"),
        ("GONE2", "FAILED", [], "Gone Two", None)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [
        ("BOTH1", "VALID", []), ("BOTH2", "VALID", []), ("NEW1", "VALID", [], "50% New Foods", "IT"),
        ("NEW2", "INSUFFICIENT_HISTORY", [], "AB_CD Ltd", "Auto"), ("NEW3", "FAILED", [], "Plain Ltd", None)])


def test_symbol_set_counts_added_removed_and_in_both(db):
    _two_runs_with_added_and_removed(db)
    conn = _ro(db)
    try:
        out = queries.get_symbol_set_diff(conn, "r-old", "r-new")
        assert out["counts"] == {"symbols_base": 4, "symbols_other": 5, "added": 3, "removed": 2, "in_both": 2}
        assert out["rows"] == [] and out["total"] is None and out["view"] is None
    finally:
        conn.close()


def test_added_and_removed_views_list_the_right_symbols_with_their_run_status(db):
    _two_runs_with_added_and_removed(db)
    conn = _ro(db)
    try:
        added = queries.get_symbol_set_diff(conn, "r-old", "r-new", view="added")
        assert [r["symbol"] for r in added["rows"]] == ["NEW1", "NEW2", "NEW3"] and added["total"] == 3
        assert {r["symbol"]: r["symbol_data_status"] for r in added["rows"]} == {
            "NEW1": "VALID", "NEW2": "INSUFFICIENT_HISTORY", "NEW3": "FAILED"}
        removed = queries.get_symbol_set_diff(conn, "r-old", "r-new", view="removed")
        assert [r["symbol"] for r in removed["rows"]] == ["GONE1", "GONE2"] and removed["total"] == 2
        assert removed["counts"] == added["counts"]
    finally:
        conn.close()


def test_set_diff_filters_sort_and_pagination_never_change_the_counts(db):
    _two_runs_with_added_and_removed(db)
    conn = _ro(db)
    try:
        def symbols(**kw):
            return [r["symbol"] for r in queries.get_symbol_set_diff(conn, "r-old", "r-new", view="added", **kw)["rows"]]
        assert symbols(sector="Auto") == ["NEW2"] and symbols(sector="UNKNOWN") == ["NEW3"] and symbols(sector="IT") == ["NEW1"]
        assert symbols(sort="symbol", sort_dir="desc") == ["NEW3", "NEW2", "NEW1"]
        assert symbols(sort="company_name") == ["NEW1", "NEW2", "NEW3"]       # "50% New Foods" < "AB_CD Ltd" < "Plain Ltd"
        assert symbols(sort="company_name", sort_dir="desc") == ["NEW3", "NEW2", "NEW1"]
        assert symbols(sort="sector") == ["NEW2", "NEW1", "NEW3"]             # Auto, IT, then the NULL sector last
        assert symbols(page=2, page_size=2) == ["NEW3"]
        filtered = queries.get_symbol_set_diff(conn, "r-old", "r-new", view="added", q="zzz")
        assert filtered["rows"] == [] and filtered["total"] == 0
        assert filtered["counts"]["added"] == 3  # the denominator is not narrowed by a filter
    finally:
        conn.close()


def test_set_diff_q_is_a_literal_substring_percent_and_underscore_are_not_wildcards(db):
    _two_runs_with_added_and_removed(db)
    conn = _ro(db)
    try:
        def symbols(q):
            return [r["symbol"] for r in queries.get_symbol_set_diff(conn, "r-old", "r-new", view="added", q=q)["rows"]]
        assert symbols("%") == ["NEW1"] and symbols("_") == ["NEW2"] and symbols("AB_CD") == ["NEW2"]
        assert symbols("\\") == [] and symbols("'; DROP TABLE scan_runs; --") == []
    finally:
        conn.close()


def test_set_diff_rejects_unknown_view_sort_and_direction(db):
    _two_runs_with_added_and_removed(db)
    conn = _ro(db)
    try:
        for kwargs in ({"view": "both"}, {"view": "added", "sort": "symbol_data_status"},
                       {"view": "added", "sort": "close; DROP"}, {"view": "added", "sort_dir": "up"}):
            with pytest.raises(ValueError):
                queries.get_symbol_set_diff(conn, "r-old", "r-new", **kwargs)
    finally:
        conn.close()


# ---------------------------------------------------------------- bars whose stored hash differs

def test_only_overlapping_bars_can_differ_a_newer_or_rolled_off_date_is_never_a_revision(db):
    # older run: d0 d1 d2   newer run: d1 d2 d3     d1 identical, d2 revised, d0 rolled off, d3 is a new session
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", [(_d(0), 100.0), (_d(1), 101.0), (_d(2), 102.0)])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", [(_d(1), 101.0), (_d(2), 102.5), (_d(3), 103.0)])])
    conn = _ro(db)
    try:
        out = queries.get_revision_summary(conn, "r-old", "r-new")
        (row,) = out["symbols"]
        assert (row["overlapping"], row["differing"]) == (2, 1)
        assert (row["only_in_older"], row["only_in_newer"]) == (1, 1)
        assert row["first_differing_date"] == row["last_differing_date"] == _d(2)
        assert row["comparable"] is True and row["not_comparable_reason"] is None
        c = out["counts"]
        assert (c["overlapping_bars"], c["differing_bars"], c["only_in_older"], c["only_in_newer"]) == (2, 1, 1, 1)
        assert c["symbols_with_differing_bars"] == 1
    finally:
        conn.close()


def test_runs_with_no_overlapping_date_have_no_revisions_only_one_sided_bars(db):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", [(_d(0), 100.0), (_d(1), 101.0)])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", [(_d(5), 100.0), (_d(6), 101.0), (_d(7), 102.0)])])
    conn = _ro(db)
    try:
        c = queries.get_revision_summary(conn, "r-old", "r-new")["counts"]
        assert (c["overlapping_bars"], c["differing_bars"]) == (0, 0)   # "0 of 0", never evidence of "no revisions"
        assert (c["only_in_older"], c["only_in_newer"]) == (2, 3)
    finally:
        conn.close()


def test_identical_runs_report_zero_differing_out_of_a_positive_denominator(db):
    bars = [(_d(i), 100.0 + i) for i in range(5)]
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", bars), ("BBB", "VALID", bars)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", bars), ("BBB", "VALID", bars)])
    conn = _ro(db)
    try:
        c = queries.get_revision_summary(conn, "r-old", "r-new")["counts"]
        assert c["overlapping_bars"] == 10 and c["differing_bars"] == 0 and c["symbols_with_differing_bars"] == 0
        assert c["comparable_symbols"] == 2 and c["not_comparable_symbols"] == 0
    finally:
        conn.close()


def test_failed_symbols_are_counted_as_not_comparable_with_a_reason(db):
    bars = [(_d(i), 100.0 + i) for i in range(3)]
    _make_run(db, "r-old", "2026-09-01T09:00:00", [
        ("OK", "VALID", bars), ("FAILNEW", "VALID", bars), ("FAILOLD", "FAILED", []), ("FAILBOTH", "FAILED", [])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [
        ("OK", "VALID", bars), ("FAILNEW", "FAILED", []), ("FAILOLD", "VALID", bars), ("FAILBOTH", "FAILED", [])])
    conn = _ro(db)
    try:
        out = queries.get_revision_summary(conn, "r-old", "r-new")
        reasons = {r["symbol"]: r["not_comparable_reason"] for r in out["symbols"]}
        assert reasons == {"FAILBOTH": "FAILED in the older run; FAILED in the newer run", "FAILNEW": "FAILED in the newer run",
                           "FAILOLD": "FAILED in the older run", "OK": None}
        c = out["counts"]
        assert (c["in_both"], c["comparable_symbols"], c["not_comparable_symbols"]) == (4, 1, 3)
        assert c["overlapping_bars"] == 3   # only the comparable symbol's bars are in the totals
    finally:
        conn.close()


def test_a_symbol_without_stored_bars_in_either_run_is_not_comparable(db):
    bars = [(_d(i), 100.0 + i) for i in range(3)]
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("NOBARS", "VALID", []), ("OK", "VALID", bars)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("NOBARS", "VALID", bars), ("OK", "VALID", bars)])
    conn = _ro(db)
    try:
        out = queries.get_revision_summary(conn, "r-old", "r-new")
        assert {r["symbol"]: r["not_comparable_reason"] for r in out["symbols"]} == {
            "NOBARS": "no stored bars in the older run", "OK": None}
    finally:
        conn.close()


def test_a_bar_from_a_different_source_never_matches(db):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", [(_d(0), 100.0, 1000, "upstox"), (_d(1), 101.0, 1000, "upstox")])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", [(_d(0), 100.0, 1000, "other-vendor"), (_d(1), 101.0, 1000, "upstox")])])
    conn = _ro(db)
    try:
        (row,) = queries.get_revision_summary(conn, "r-old", "r-new")["symbols"]
        assert (row["overlapping"], row["differing"]) == (1, 0)           # only d1 (same source) overlaps, and is identical
        assert (row["only_in_older"], row["only_in_newer"]) == (1, 1)     # d0 exists in both runs but under different sources
    finally:
        conn.close()


def test_a_symbol_whose_every_bar_differs_is_a_count_with_no_cause(db):
    # a split-style rewrite of the whole history: the page can only say how many bars differ, never why
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("SPLIT", "VALID", [(_d(i), 200.0 + i) for i in range(6)]),
                                                    ("OK", "VALID", [(_d(i), 50.0 + i) for i in range(6)])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("SPLIT", "VALID", [(_d(i), 100.0 + i / 2) for i in range(6)]),
                                                    ("OK", "VALID", [(_d(i), 50.0 + i) for i in range(6)])])
    conn = _ro(db)
    try:
        out = queries.get_revision_summary(conn, "r-old", "r-new")
        by_symbol = {r["symbol"]: r for r in out["symbols"]}
        assert (by_symbol["SPLIT"]["overlapping"], by_symbol["SPLIT"]["differing"]) == (6, 6)
        assert (by_symbol["SPLIT"]["first_differing_date"], by_symbol["SPLIT"]["last_differing_date"]) == (_d(0), _d(5))
        assert by_symbol["OK"]["differing"] == 0
        assert out["counts"]["symbols_with_differing_bars"] == 1 and out["counts"]["differing_bars"] == 6
        keys = {k.lower() for k in by_symbol["SPLIT"]} | {k.lower() for k in out["counts"]}
        assert not any(w in k for k in keys for w in ("cause", "split", "adjust", "reason_for_change", "revision_type"))
    finally:
        conn.close()


def test_every_denominator_is_returned_for_a_mixed_pair_of_runs(db):
    bars_a = [(_d(i), 100.0 + i) for i in range(4)]
    bars_b = [(_d(i + 1), 100.0 + i + 1) for i in range(4)]          # shifted by one session: 3 overlap
    revised = [(d, c + 0.5 if d == _d(2) else c) for d, c in bars_b]  # one overlapping bar differs
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("A", "VALID", bars_a), ("B", "FAILED", []), ("GONE", "VALID", bars_a)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("A", "VALID", revised), ("B", "VALID", bars_b), ("NEW", "VALID", bars_b)])
    conn = _ro(db)
    try:
        counts = queries.get_revision_summary(conn, "r-old", "r-new")["counts"]
        assert counts == {
            "symbols_base": 3, "symbols_other": 3, "added": 1, "removed": 1, "in_both": 2,
            "comparable_symbols": 1, "not_comparable_symbols": 1,
            "overlapping_bars": 3, "differing_bars": 1, "symbols_with_differing_bars": 1,
            "only_in_older": 1, "only_in_newer": 1}
    finally:
        conn.close()


def test_the_comparison_uses_stored_hashes_only_never_a_recomputed_one(db):
    # Same hash text stored in both runs for DIFFERENT prices -> not a difference; different hash text for the same
    # prices -> a difference. Only string equality of the stored content_hash decides.
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("SAMEHASH", "VALID", []), ("DIFFHASH", "VALID", [])], end="RUNNING")
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("SAMEHASH", "VALID", []), ("DIFFHASH", "VALID", [])], end="RUNNING")
    conn = connection.get_connection(db)
    try:
        def put(run, symbol, close, stored_hash):
            conn.execute(
                "INSERT INTO price_fetch_snapshots (scan_run_id, symbol, trading_date, source, fetched_at_ist, open, high, low, "
                "close, volume, content_hash, candle_validation_status) VALUES (?, ?, ?, 'upstox', 'x', '1.00', '2.00', '0.50', ?, 10, ?, 'VALID')",
                (run, symbol, _d(0), close, stored_hash))
        put("r-old", "SAMEHASH", "100.00", "a" * 64)
        put("r-new", "SAMEHASH", "999.00", "a" * 64)      # different prices, identical stored hash text
        put("r-old", "DIFFHASH", "100.00", "b" * 64)
        put("r-new", "DIFFHASH", "100.00", "c" * 64)      # identical prices, different stored hash text
        conn.commit()
    finally:
        conn.close()
    ro = _ro(db)
    try:
        by_symbol = {r["symbol"]: r for r in queries.get_revision_summary(ro, "r-old", "r-new")["symbols"]}
        assert by_symbol["SAMEHASH"]["differing"] == 0 and by_symbol["DIFFHASH"]["differing"] == 1
    finally:
        ro.close()


def test_the_new_queries_never_import_or_call_a_hash_function():
    source = inspect.getsource(queries)
    assert "hashlib" not in source and "compute_content_hash" not in source and "sha256" not in source.lower()


def test_all_new_query_text_is_parameterized(db):
    section = inspect.getsource(queries).split("# Snapshot Audit queries (Phase 3)")[1]
    assert not re.search(r"""f["'][^"']*\{(base|other|run_id|symbol|q|sector)\b""", section)
    assert "format(" not in section and "% (" not in section
    assert ":base" in queries.REVISION_SUMMARY_SQL and ":other" in queries.REVISION_SUMMARY_SQL


def test_the_new_queries_work_on_a_read_only_connection_and_cannot_write(db):
    bars = [(_d(i), 100.0 + i) for i in range(3)]
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", bars)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", bars), ("BBB", "VALID", bars)])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    conn = _ro(db)
    try:
        queries.get_eligible_runs(conn)
        queries.get_ineligible_runs(conn)
        queries.get_symbol_set_diff(conn, "r-old", "r-new", view="added")
        queries.get_revision_summary(conn, "r-old", "r-new")
        queries.get_symbol_revisions(conn, "r-old", "r-new", "AAA")
        for statement in ("UPDATE price_fetch_snapshots SET close = '1.00'", "DELETE FROM symbol_scan_results",
                          "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) VALUES ('x', 'y', 'RUNNING', 'BLOCKED_B2')",
                          "CREATE TABLE should_not_exist (x)"):
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(statement)
    finally:
        conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


# ---------------------------------------------------------------- per-symbol revisions and the 300-bar cap

def test_symbol_revisions_show_both_runs_stored_values_side_by_side(db):
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", [(_d(0), 100.0, 1000), (_d(1), 101.0, 1000), (_d(2), 102.0, 1000)])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", [(_d(1), 101.0, 1000), (_d(2), 102.5, 2000), (_d(3), 103.0, 1000)])])
    conn = _ro(db)
    try:
        out = queries.get_symbol_revisions(conn, "r-old", "r-new", "AAA")
        assert (out["overlapping"], out["differing"], out["only_in_older"], out["only_in_newer"]) == (2, 1, 1, 1)
        assert out["truncated"] is False and out["cap"] == 300 == queries.REVISION_ROW_CAP
        (row,) = out["rows"]
        assert row["trading_date"] == _d(2) and row["source"] == "upstox"
        assert (row["base_close"], row["other_close"]) == ("102.00", "102.50")      # stored text, as written
        assert (row["base_volume"], row["other_volume"]) == (1000, 2000)
        assert row["base_hash"] != row["other_hash"] and len(row["base_hash"]) == len(row["other_hash"]) == 64
        assert row["base_hash"] == compute_content_hash(_d(2), 101.0, 104.0, 100.0, 102.0, 1000)  # a real stored hash
    finally:
        conn.close()


def _wide_symbol_runs(db, n_differing, n_total=None):
    n_total = n_total or n_differing
    old = [(_d(i), 100.0 + i) for i in range(n_total)]
    new = [(_d(i), (100.0 + i) + (0.5 if i < n_differing else 0)) for i in range(n_total)]
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("WIDE", "VALID", old)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("WIDE", "VALID", new)])


def test_symbol_revisions_are_capped_at_300_with_a_truncated_flag_and_the_real_total(db):
    _wide_symbol_runs(db, 350, n_total=360)
    conn = _ro(db)
    try:
        out = queries.get_symbol_revisions(conn, "r-old", "r-new", "WIDE")
        assert len(out["rows"]) == 300 and out["truncated"] is True and out["cap"] == 300
        assert out["differing"] == 350 and out["overlapping"] == 360          # the real totals, not the capped length
        dates = [r["trading_date"] for r in out["rows"]]
        assert dates == sorted(dates) and dates[0] == _d(0) and dates[-1] == _d(299)   # the oldest 300 differing bars
        assert len(queries.get_symbol_revisions(conn, "r-old", "r-new", "WIDE", limit=10_000)["rows"]) == 300  # never more than the cap
        small = queries.get_symbol_revisions(conn, "r-old", "r-new", "WIDE", limit=5)
        assert len(small["rows"]) == 5 and small["truncated"] is True and small["differing"] == 350 and small["cap"] == 5
    finally:
        conn.close()


@pytest.mark.parametrize("n, truncated", [(299, False), (300, False), (301, True)])
def test_truncation_flag_at_the_cap_boundary(db, n, truncated):
    _wide_symbol_runs(db, n)
    conn = _ro(db)
    try:
        out = queries.get_symbol_revisions(conn, "r-old", "r-new", "WIDE")
        assert out["truncated"] is truncated and out["differing"] == n and len(out["rows"]) == min(n, 300)
    finally:
        conn.close()


def test_symbol_revisions_for_a_symbol_with_no_bars_or_no_revisions_are_empty_not_an_error(db):
    bars = [(_d(i), 100.0 + i) for i in range(3)]
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("SAME", "VALID", bars), ("FAIL", "FAILED", [])])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("SAME", "VALID", bars), ("FAIL", "FAILED", [])])
    conn = _ro(db)
    try:
        same = queries.get_symbol_revisions(conn, "r-old", "r-new", "SAME")
        assert same["rows"] == [] and same["differing"] == 0 and same["overlapping"] == 3 and same["truncated"] is False
        failed = queries.get_symbol_revisions(conn, "r-old", "r-new", "FAIL")
        assert (failed["rows"], failed["overlapping"], failed["differing"], failed["truncated"]) == ([], 0, 0, False)
        unknown = queries.get_symbol_revisions(conn, "r-old", "r-new", "NOPE")
        assert unknown["rows"] == [] and unknown["overlapping"] == 0
    finally:
        conn.close()


# ---------------------------------------------------------------- the demo seed (expected numbers come from the seed's constants)

@pytest.fixture
def demo_db(monkeypatch, tmp_path):
    canonical, demo = tmp_path / "equity_intel.db", tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", canonical)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    seed.seed_demo_database(demo)
    return demo


def test_demo_runs_are_split_into_eligible_and_ineligible_as_documented(demo_db):
    conn = _ro(demo_db)
    try:
        eligible = queries.get_eligible_runs(conn)
        assert [r["run_id"] for r in eligible["runs"]] == ["r-demo-latest-complete", "r-demo-prev-complete", "r-demo-old-complete"]
        ineligible = {r["run_id"]: r["kind"] for r in queries.get_ineligible_runs(conn)["runs"]}
        assert ineligible == {"r-demo-smoke": "SMOKE", "r-demo-aborted": "ABORTED", "r-demo-running": "RUNNING"}
    finally:
        conn.close()


def test_demo_previous_vs_latest_revisions_match_the_seed_rule(demo_db):
    # Expected numbers are derived from the seed's own constants and rule functions, never typed in.
    symbols = [(i, s[0], s[3]) for i, s in enumerate(seed.FAKE_SYMBOLS)]
    non_failed = [(i, sym, status) for i, sym, status in symbols if status != "FAILED"]
    expected_overlap = sum(len(seed._bar_dates_for(status)) for _i, _s, status in non_failed)
    expected_differing = sum(
        1 for i, _s, status in non_failed
        if seed.REVISED_DATE in seed._bar_dates_for(status)
        and seed._bar_values(i, seed.REVISED_DATE, revised=True) != seed._bar_values(i, seed.REVISED_DATE, revised=False))
    assert expected_differing > 0 and expected_overlap > 0
    conn = _ro(demo_db)
    try:
        out = queries.get_revision_summary(conn, "r-demo-prev-complete", "r-demo-latest-complete")
        c = out["counts"]
        assert c["symbols_base"] == c["symbols_other"] == c["in_both"] == len(seed.FAKE_SYMBOLS)
        assert (c["added"], c["removed"]) == (0, 0)
        assert c["comparable_symbols"] == len(non_failed)
        assert c["not_comparable_symbols"] == len(seed.FAKE_SYMBOLS) - len(non_failed)
        assert c["overlapping_bars"] == expected_overlap and c["differing_bars"] == expected_differing
        assert c["symbols_with_differing_bars"] == expected_differing        # one revised date, so one differing bar each
        assert (c["only_in_older"], c["only_in_newer"]) == (0, 0)
        revised = sorted(r["symbol"] for r in out["symbols"] if r["differing"])
        assert revised == sorted(sym for i, sym, status in non_failed
                                 if seed.REVISED_DATE in seed._bar_dates_for(status)
                                 and seed._bar_values(i, seed.REVISED_DATE, revised=True) != seed._bar_values(i, seed.REVISED_DATE, revised=False))
        assert all(r["first_differing_date"] == seed.REVISED_DATE for r in out["symbols"] if r["differing"])
    finally:
        conn.close()


def test_demo_old_vs_previous_have_no_overlapping_date_so_every_bar_is_one_sided(demo_db):
    non_failed = [s for s in seed.FAKE_SYMBOLS if s[3] != "FAILED"]
    expected_older = len(non_failed)                                   # the old run stores one bar per non-FAILED symbol
    expected_newer = sum(len(seed._bar_dates_for(s[3])) for s in non_failed)
    conn = _ro(demo_db)
    try:
        c = queries.get_revision_summary(conn, "r-demo-old-complete", "r-demo-prev-complete")["counts"]
        assert c["overlapping_bars"] == 0 and c["differing_bars"] == 0
        assert (c["only_in_older"], c["only_in_newer"]) == (expected_older, expected_newer)
    finally:
        conn.close()


# ---------------------------------------------------------------- query plan guard and the 500 x 260 benchmark

BENCH_SYMBOLS, BENCH_BARS = 500, 260
PLAN_BAR_LOOKUP = re.compile(
    r"SEARCH b USING (?:COVERING )?INDEX sqlite_autoindex_price_fetch_snapshots_1 "
    r"\(scan_run_id=\? AND symbol=\? AND trading_date=\? AND source=\?\)")


def _plan(conn, sql, params):
    return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()]


def _plan_problems(plan_lines):
    """Lines that would mean a scan of price_fetch_snapshots (or of its aliases) instead of a primary-key search."""
    return [line for line in plan_lines if re.match(r"SCAN (price_fetch_snapshots|o|b)\b", line)]


def test_revision_summary_plan_looks_the_other_run_up_by_primary_key_with_no_snapshot_scan(db):
    bars = [(_d(i), 100.0 + i) for i in range(5)]
    _make_run(db, "r-old", "2026-09-01T09:00:00", [("AAA", "VALID", bars)])
    _make_run(db, "r-new", "2026-09-02T09:00:00", [("AAA", "VALID", bars)])
    conn = _ro(db)
    try:
        plan = _plan(conn, queries.REVISION_SUMMARY_SQL, {"base": "r-old", "other": "r-new"})
        print("\nEXPLAIN QUERY PLAN (small db):\n  " + "\n  ".join(plan))
        assert any(PLAN_BAR_LOOKUP.search(line) for line in plan), plan
        assert _plan_problems(plan) == [], plan
        # every touch of the snapshots table is a SEARCH (an index range or lookup), never a SCAN
        touching = [line for line in plan if "price_fetch_snapshots" in line]
        assert touching and all(line.startswith("SEARCH") for line in touching), touching
    finally:
        conn.close()


def _build_bench_db(db):
    """500 symbols x 260 bars per run. The newer run's window is shifted by one session. Revisions: every 20th
    overlapping bar of every 10th symbol, plus a split-style rewrite of every bar of every 50th symbol (offset 7).
    Every 97th symbol (offset 5) is FAILED in the newer run; 5 symbols are only in the older run, 5 only in the newer."""
    def spec(index, run):
        return {"failed": run == "new" and index % 97 == 5}
    conn = connection.get_connection(db)
    expected = {"overlapping": 0, "differing": 0, "with_differing": 0, "only_older": 0, "only_newer": 0,
                "comparable": 0, "not_comparable": 0}
    try:
        for run_id, started in (("r-old", "2026-09-01T09:00:00"), ("r-new", "2026-09-02T09:00:00")):
            seed._insert_scan_run(conn, run_id, started)
        symbols_old = [f"SYM{i:04d}" for i in range(BENCH_SYMBOLS)] + [f"GONE{i}" for i in range(5)]
        symbols_new = [f"SYM{i:04d}" for i in range(BENCH_SYMBOLS)] + [f"NEW{i}" for i in range(5)]
        for run_id, names, run in (("r-old", symbols_old, "old"), ("r-new", symbols_new, "new")):
            rows, snaps = [], []
            for index, symbol in enumerate(names):
                failed = spec(index, run)["failed"] if symbol.startswith("SYM") else False
                seed._insert_symbol_result(conn, run_id, symbol, symbol + " Co", "IT", "FAILED" if failed else "VALID", None, NO_FLAGS)
                if failed:
                    continue
                first = 0 if run == "old" else 1
                for k in range(BENCH_BARS):
                    day = first + k
                    close = 100.0 + (index % 40) + day * 0.01
                    if run == "new" and symbol.startswith("SYM") and day < BENCH_BARS:      # an overlapping date
                        if index % 50 == 7:
                            close += 1.0                                                      # split-style: every overlapping bar differs
                        elif index % 10 == 0 and day % 20 == 0:
                            close += 0.5                                                      # sparse revisions
                    prices = [f"{close - 1:.2f}", f"{close + 2:.2f}", f"{close - 2:.2f}", f"{close:.2f}"]
                    snaps.append((run_id, symbol, _d(day), "upstox", "2026-09-01T09:00:00+05:30", *prices, 1000,
                                  compute_content_hash(_d(day), *prices, 1000), "VALID"))
            conn.executemany(
                "INSERT INTO price_fetch_snapshots (scan_run_id, symbol, trading_date, source, fetched_at_ist, open, high, low, "
                "close, volume, content_hash, candle_validation_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", snaps)
        for run_id, started in (("r-old", "2026-09-01T09:00:00"), ("r-new", "2026-09-02T09:00:00")):
            seed._complete_run(conn, run_id, started, "2026-10-01", {s: 0 for s in queries.STATUS_VALUES}, {k: 0 for k in NO_FLAGS},
                               requested=BENCH_SYMBOLS, successful=BENCH_SYMBOLS, failed=0)
        conn.commit()
    finally:
        conn.close()
    # expected numbers, derived from the generation rule above (not from the query under test)
    for index in range(BENCH_SYMBOLS):
        if index % 97 == 5:
            expected["not_comparable"] += 1
            continue
        expected["comparable"] += 1
        overlap_days = range(1, BENCH_BARS)                    # old days 0..259, new days 1..260 -> days 1..259 overlap
        expected["overlapping"] += len(overlap_days)
        expected["only_older"] += 1
        expected["only_newer"] += 1
        if index % 50 == 7:
            differing = len(overlap_days)
        elif index % 10 == 0:
            differing = sum(1 for day in overlap_days if day % 20 == 0)
        else:
            differing = 0
        expected["differing"] += differing
        expected["with_differing"] += 1 if differing else 0
    return expected


@pytest.mark.slow
def test_benchmark_500_symbols_by_260_bars_revision_summary_is_correct_indexed_and_timed(db):
    expected = _build_bench_db(db)
    conn = _ro(db)
    try:
        rows_per_run = [conn.execute("SELECT COUNT(*) FROM price_fetch_snapshots WHERE scan_run_id = ?", (r,)).fetchone()[0]
                        for r in ("r-old", "r-new")]
        assert all(n > 120_000 for n in rows_per_run), rows_per_run   # about 500 x 260 stored bars in each run

        plan = _plan(conn, queries.REVISION_SUMMARY_SQL, {"base": "r-old", "other": "r-new"})
        print("\nEXPLAIN QUERY PLAN (500 x 260 db):\n  " + "\n  ".join(plan))
        assert any(PLAN_BAR_LOOKUP.search(line) for line in plan), plan
        assert _plan_problems(plan) == [], plan

        timings = []
        for _ in range(5):
            started = time.perf_counter()
            out = queries.get_revision_summary(conn, "r-old", "r-new")
            timings.append(time.perf_counter() - started)
        c = out["counts"]
        print(f"\nBENCHMARK get_revision_summary, 500 symbols x 260 bars x 2 runs ({sum(rows_per_run)} stored bars): "
              f"min {min(timings) * 1000:.0f} ms | median {statistics.median(timings) * 1000:.0f} ms | max {max(timings) * 1000:.0f} ms"
              f" | runs: {[round(t * 1000) for t in timings]} ms")
        assert (c["overlapping_bars"], c["differing_bars"], c["symbols_with_differing_bars"]) == (
            expected["overlapping"], expected["differing"], expected["with_differing"])
        assert (c["only_in_older"], c["only_in_newer"]) == (expected["only_older"], expected["only_newer"])
        assert (c["comparable_symbols"], c["not_comparable_symbols"]) == (expected["comparable"], expected["not_comparable"])
        assert (c["added"], c["removed"], c["in_both"]) == (5, 5, BENCH_SYMBOLS)
        assert expected["differing"] > 0 and expected["with_differing"] > 10
        assert max(timings) < 30, "a primary-key join of two 130k-row runs must not take anywhere near this long"
    finally:
        conn.close()

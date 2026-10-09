"""aggregates.get_data_quality: every warning names its layer, and each layer is counted on its own.

The old merged fields (symbols_*, warning_counts, issues) keep their values; `layers` is additive. The data below
is small enough to derive every expected number by hand:

  ScanRun r1 (5 symbols)                     E4 scan e4-1 (5 quality rows)
  A  VALID                                   A  VALID, complete
  B  FAILED, history_gaps                    B  INSUFFICIENT_HISTORY, no full high window
  C  VALID, price_break_detected flag        C  VALID, a break on 2026-03-01 (ratio 0.4)
  D  VALID                                   D  VALID, volume not usable
  E  STALE, corporate_action_review          (no E4 row)
  (not in the scan run)                      F  STALE
"""
import json

import pytest

from dashboard import aggregates, queries
from dashboard.app import create_app
from equity_intel.persistence import connection
from equity_intel.tests.test_dashboard_exception_queries import _add_run, _ro, db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_freshness_queries import _add_e4_scan

SCANRUN_CODES = {"VALID", "FAILED", "STALE", "INSUFFICIENT_HISTORY", "history_gaps", "corporate_action_review",
                 "price_break_detected", "non_eq_series"}


def _e4_row(db, symbol, status="VALID", *, reason=None, w52=1, volume=1, break_date=None, ratio=None):
    conn = connection.connect(db)
    try:
        conn.execute("INSERT INTO e4_data_quality_results(scan_id,symbol,status,reason,n_bars,w52_complete,break_date,break_ratio,volume_usable) "
                     "VALUES('e4-1',?,?,?,252,?,?,?,?)", (symbol, status, reason, w52, break_date, ratio, volume))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def layered(db):
    _add_run(db, "r1", "2026-10-02T09:00:00", symbols=[
        ("A", "VALID", {}), ("B", "FAILED", {"history_gaps": True}), ("C", "VALID", {"price_break_detected": True}),
        ("D", "VALID", {}), ("E", "STALE", {"corporate_action_review": True})])
    _add_e4_scan(db, "e4-1", "2026-10-02T10:00:00+00:00", asof="2026-10-01", acq="acq-1", quality=[], features=1)
    _e4_row(db, "A")
    _e4_row(db, "B", "INSUFFICIENT_HISTORY", reason="40 bars; 252 required", w52=0)
    _e4_row(db, "C", break_date="2026-03-01", ratio=0.4)
    _e4_row(db, "D", volume=0)
    _e4_row(db, "F", "STALE", reason="last observation 2026-09-30, run as-of 2026-10-01")
    return db


def _quality(db, symbol=None, e4=True):
    conn = _ro(db)
    try:
        return aggregates.get_data_quality(conn, "r1", queries.get_latest_e4_scan(conn) if e4 else None, symbol)
    finally:
        conn.close()


def _by_symbol(dq):
    return {i["symbol"]: i for i in dq["issues"]}


# ---------------------------------------------------------------- layer tags

def test_every_warning_names_its_layer_and_the_layer_matches_the_code(layered):
    dq = _quality(layered)
    warnings = [w for i in dq["issues"] for w in i["warnings"]]
    assert warnings and all(w["layer"] in ("ScanRun", "E4") for w in warnings)
    for w in warnings:
        assert (w["layer"] == "E4") == w["code"].startswith("e4_"), w
        assert (w["layer"] == "ScanRun") == (w["code"] in SCANRUN_CODES), w


def test_the_warnings_of_each_symbol_are_the_hand_derived_ones(layered):
    issues = _by_symbol(_quality(layered))
    assert set(issues) == {"B", "C", "D", "E"}                                       # A is clean; F is not in the scan run
    codes = {s: [(w["layer"], w["code"]) for w in i["warnings"]] for s, i in issues.items()}
    assert codes == {
        "B": [("ScanRun", "FAILED"), ("ScanRun", "history_gaps"), ("E4", "e4_INSUFFICIENT_HISTORY"), ("E4", "e4_no_full_high_window")],
        "C": [("ScanRun", "price_break_detected")],
        "D": [("E4", "e4_volume_unusable")],
        "E": [("ScanRun", "STALE"), ("ScanRun", "corporate_action_review")],
    }


def test_the_price_break_warning_keeps_its_full_message_and_tags_the_e4_part_separately(layered):
    warning = _by_symbol(_quality(layered))["C"]["warnings"][0]
    assert warning["message"] == "close-to-close jump consistent with an unadjusted split/bonus; E4 break on 2026-03-01 (close ratio 0.4000)"
    assert warning["parts"] == [
        {"layer": "ScanRun", "text": "close-to-close jump consistent with an unadjusted split/bonus"},
        {"layer": "E4", "code": "e4_break", "text": "break on 2026-03-01 (close ratio 0.4000)"}]       # the layer tag supplies the word E4
    assert warning["layer"] == "ScanRun"


def test_a_price_break_flag_without_an_e4_break_has_no_parts(db):
    _add_run(db, "r1", "2026-10-02T09:00:00", symbols=[("C", "VALID", {"price_break_detected": True})])
    _add_e4_scan(db, "e4-1", "2026-10-02T10:00:00+00:00", asof="2026-10-01", quality=["VALID"], features=1)
    warning = _by_symbol(_quality(db))["C"]["warnings"][0]
    assert warning["message"] == "close-to-close jump consistent with an unadjusted split/bonus" and "parts" not in warning


def test_an_e4_break_without_the_scanrun_flag_is_a_separate_e4_warning(db):
    _add_run(db, "r1", "2026-10-02T09:00:00", symbols=[("C", "VALID", {})])
    _add_e4_scan(db, "e4-1", "2026-10-02T10:00:00+00:00", asof="2026-10-01", quality=[], features=1)
    _e4_row(db, "C", break_date="2026-03-01", ratio=0.4)
    warnings = _by_symbol(_quality(db))["C"]["warnings"]
    assert [(w["layer"], w["code"]) for w in warnings] == [("E4", "e4_break")] and "parts" not in warnings[0]


# ---------------------------------------------------------------- per-layer counts

def test_each_layer_is_counted_on_its_own(layered):
    layers = _quality(layered)["layers"]
    assert layers["scanrun"] == {
        "symbols_total": 5, "symbols_with_warnings": 3, "symbols_without_warning": 2,       # B, C, E; A and D have no ScanRun warning
        "warning_counts": {"FAILED": 1, "history_gaps": 1, "price_break_detected": 1, "STALE": 1, "corporate_action_review": 1}}
    assert layers["e4"] == {
        "scan_id": "e4-1", "symbols_total": 5, "symbols_with_warnings": 4, "symbols_without_warning": 1,   # B, C, D, F; A is clean
        "warning_counts": {"e4_INSUFFICIENT_HISTORY": 1, "e4_no_full_high_window": 1, "e4_break": 1, "e4_volume_unusable": 1, "e4_STALE": 1},
        "not_listed_with_warnings": 1}                                                       # F has an E4 warning but is not in the scan run


def test_the_per_layer_counts_are_not_the_merged_counts_and_are_never_summed(layered):
    dq = _quality(layered)
    assert (dq["symbols_total"], dq["symbols_with_warnings"], dq["symbols_without_warning"]) == (5, 4, 1)      # the merged meaning is unchanged
    assert dq["layers"]["scanrun"]["symbols_with_warnings"] == 3 and dq["layers"]["e4"]["symbols_with_warnings"] == 4
    assert "symbols_with_warnings" not in dq["layers"] and not [k for k in dq["layers"] if "total" in k or "sum" in k]


def test_the_merged_fields_keep_the_values_they_had_before_the_layers_were_added(layered):
    dq = _quality(layered)
    assert dq["warning_counts"] == {
        "FAILED": 1, "history_gaps": 1, "e4_INSUFFICIENT_HISTORY": 1, "e4_no_full_high_window": 1, "price_break_detected": 1,
        "e4_volume_unusable": 1, "STALE": 1, "corporate_action_review": 1}                    # no e4_break: C's break is a part of its price-break warning
    assert sorted(i["symbol"] for i in dq["issues"]) == ["B", "C", "D", "E"]                  # the order is the table's, which this change leaves alone
    assert set(dq) == {"symbols_total", "symbols_with_warnings", "symbols_without_warning", "warning_counts", "issues", "layers"}


def test_the_e4_total_is_the_number_of_quality_rows_from_get_e4_status_counts(layered):
    conn = _ro(layered)
    try:
        assert queries.get_e4_status_counts(conn, "e4-1")["total"] == 5
    finally:
        conn.close()
    assert _quality(layered)["layers"]["e4"]["symbols_total"] == 5
    _e4_row(layered, "G")                                                                 # a sixth quality row, clean
    layers = _quality(layered)["layers"]
    assert layers["e4"]["symbols_total"] == 6 and layers["e4"]["symbols_without_warning"] == 2 and layers["scanrun"]["symbols_total"] == 5


def test_there_is_no_e4_layer_without_a_complete_e4_scan(db):
    _add_run(db, "r1", "2026-10-02T09:00:00", symbols=[("A", "VALID", {}), ("B", "FAILED", {})])
    dq = _quality(db, e4=False)
    assert dq["layers"]["e4"] is None and dq["layers"]["scanrun"]["symbols_with_warnings"] == 1
    assert all(w["layer"] == "ScanRun" for i in dq["issues"] for w in i["warnings"])


def test_a_single_symbol_request_counts_that_symbol_in_each_layer(layered):
    b = _quality(layered, "B")["layers"]
    assert b["scanrun"]["symbols_total"] == 1 and b["scanrun"]["symbols_with_warnings"] == 1
    assert b["e4"]["symbols_total"] == 1 and b["e4"]["symbols_with_warnings"] == 1 and b["e4"]["not_listed_with_warnings"] == 0
    f = _quality(layered, "F")["layers"]
    assert f["scanrun"]["symbols_total"] == 0 and f["e4"]["symbols_with_warnings"] == 1 and f["e4"]["not_listed_with_warnings"] == 1


# ---------------------------------------------------------------- the summary route: additive only

def test_the_summary_keeps_every_key_it_had_and_adds_only_the_layers(layered):
    body = create_app(demo=False, db_path=layered).test_client().get("/api/equity/summary").get_json()
    assert {"demo", "run", "outdated", "e4_scan", "breadth", "history", "data_quality", "safety"} <= set(body)
    assert set(body) == {"demo", "run", "outdated", "e4_scan", "breadth", "history", "data_quality", "safety"}      # no new top-level key
    dq = body["data_quality"]
    assert {"symbols_total", "symbols_with_warnings", "symbols_without_warning", "warning_counts", "issues"} <= set(dq)
    assert set(dq) - {"symbols_total", "symbols_with_warnings", "symbols_without_warning", "warning_counts", "issues"} == {"layers"}
    for issue in dq["issues"]:
        assert {"symbol", "company_name", "sector", "status", "warnings"} == set(issue)
        assert all({"code", "message"} <= set(w) and set(w) - {"code", "message"} <= {"layer", "parts"} for w in issue["warnings"])
    assert dq["layers"]["e4"]["symbols_total"] == 5 and dq["layers"]["scanrun"]["symbols_total"] == 5
    assert json.dumps(body)                                                               # still plain JSON

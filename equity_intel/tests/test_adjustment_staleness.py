"""E4 reads a stored acquisition run whose prices were adjusted at fetch time.
A corporate action effective on/after that fetch leaves the run on the pre-event
basis; the scan must flag it, withhold features, and be cleared only by a new run."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import equity_intel.persistence.connection as persistence_connection
import equity_intel.persistence.db_path_guard as db_path_guard
from equity_intel.features.runner import run_feature_scan
from equity_intel.tests.test_features import CFG, _seed

HEADER = "symbol,isin,event_type,effective_date,reason,reviewer,review_state\n"


def _utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _review(tmp_path, *rows):
    path = tmp_path / "review.csv"
    path.write_text(HEADER + "".join(rows))
    return path


def _split(date, state="OPEN"):
    return f"AAA,,SPLIT,{date},1:5 split,tester,{state}\n"


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    _seed(path)  # acquisition run r1, started 2026-01-01T00:00:00 UTC (05:30 IST)
    return path


def _reacquire(database, run_id, started_at):
    """Stand-in for a fresh scripts/equity_data_acquisition.py run: a new run_id with its own rows."""
    with persistence_connection.connect(database) as c:
        report = c.execute("SELECT status,report_json FROM acquisition_runs WHERE run_id='r1'").fetchone()
        c.execute("INSERT INTO acquisition_runs VALUES(?,?,?,?,?)", (run_id, started_at, started_at, report["status"], report["report_json"]))
        c.execute("INSERT INTO instrument_mappings SELECT ?,symbol,exchange,instrument_key,instrument_type,mapping_status,mapping_source,"
                  "mapping_error,company_name,industry,series,isin FROM instrument_mappings WHERE run_id='r1'", (run_id,))
        c.execute("INSERT INTO symbol_acquisition_results SELECT ?,symbol,status,reason,instrument_key,observation_count,first_date,"
                  "last_date,requested_start,requested_end,validation_status FROM symbol_acquisition_results WHERE run_id='r1'", (run_id,))
        c.execute("INSERT INTO acquired_observations SELECT ?,symbol,trading_date,open,high,low,close,volume,source_vendor,source_endpoint,"
                  "retrieval_timestamp,instrument_key,exchange,calendar_status,adjustment_status,? FROM acquired_observations WHERE run_id='r1'",
                  (run_id, run_id))
        c.execute("INSERT INTO acquired_benchmark SELECT ?,benchmark_key,trading_date,close,source_vendor,retrieval_timestamp "
                  "FROM acquired_benchmark WHERE run_id='r1'", (run_id,))


def _quality(database, scan_id):
    with persistence_connection.connect(database) as c:
        q = c.execute("SELECT status,reason FROM e4_data_quality_results WHERE scan_id=? AND symbol='AAA'", (scan_id,)).fetchone()
        features = c.execute("SELECT COUNT(*) FROM e4_feature_sets WHERE scan_id=? AND symbol='AAA'", (scan_id,)).fetchone()[0]
        return q["status"], q["reason"], features


def test_stored_run_is_flagged_after_a_later_ex_date_and_cleared_only_by_a_new_run(database, tmp_path):
    # 1. run fetched 2026-01-01; no known action yet -> clean
    empty = _review(tmp_path)
    before = run_feature_scan(CFG, db_path=database, corporate_action_review_path=empty, now=_utc("2026-01-02T06:00:00"))
    assert _quality(database, before["scan_id"]) == ("VALID", None, 1) and before["stale_adjustment_basis"] == []

    # 2. split effective 2026-01-05 becomes known; ex-date still in the future -> still valid
    review = _review(tmp_path, _split("2026-01-05"))
    pending = run_feature_scan(CFG, db_path=database, corporate_action_review_path=review, now=_utc("2026-01-04T06:00:00"))
    assert _quality(database, pending["scan_id"])[0] == "VALID"

    # 3. ex-date has passed; E4 re-read of the same stored run is detected, features withheld
    after = run_feature_scan(CFG, db_path=database, corporate_action_review_path=review, now=_utc("2026-01-06T06:00:00"))
    status, reason, features = _quality(database, after["scan_id"])
    assert status == "STALE" and features == 0
    assert reason.startswith("ADJUSTMENT_BASIS_STALE") and "r1" in reason and "SPLIT effective 2026-01-05" in reason
    assert after["stale_adjustment_basis"] == ["AAA"] and after["status"] == "COMPLETE" and after["quality"]["STALE"] == 1
    assert after["acquisition_run_id"] == "r1"

    # 4. auditable: each scan records the review file it used; earlier scans are untouched
    with persistence_connection.connect(database) as c:
        hashes = {r["scan_id"]: r["corporate_action_review_sha256"] for r in c.execute("SELECT scan_id,corporate_action_review_sha256 FROM e4_scan_runs")}
        assert hashes[before["scan_id"]] != hashes[after["scan_id"]] and hashes[pending["scan_id"]] == hashes[after["scan_id"]]
    assert _quality(database, before["scan_id"]) == ("VALID", None, 1)

    # 5. refresh is an explicit new acquisition run fetched after the ex-date; the old run is kept as-is
    _reacquire(database, "r2", "2026-01-06T05:00:00")
    refreshed = run_feature_scan(CFG, db_path=database, corporate_action_review_path=review, now=_utc("2026-01-06T06:00:00"))
    assert refreshed["acquisition_run_id"] == "r2" and refreshed["stale_adjustment_basis"] == []
    assert _quality(database, refreshed["scan_id"]) == ("VALID", None, 1)
    with persistence_connection.connect(database) as c:
        assert c.execute("SELECT COUNT(*) FROM acquired_observations WHERE run_id='r1'").fetchone()[0] == 252
        assert c.execute("SELECT acquisition_run_id FROM e4_scan_runs WHERE scan_id=?", (after["scan_id"],)).fetchone()[0] == "r1"


def test_fetch_on_the_ex_date_is_flagged_and_cleared_by_a_fetch_the_next_day(database, tmp_path):
    review = _review(tmp_path, _split("2026-01-01"))  # r1 fetched 2026-01-01 IST: same day, adjustment status unknown
    result = run_feature_scan(CFG, db_path=database, corporate_action_review_path=review, now=_utc("2026-01-01T12:00:00"))
    assert result["stale_adjustment_basis"] == ["AAA"]
    _reacquire(database, "r2", "2026-01-02T05:00:00")
    assert run_feature_scan(CFG, db_path=database, corporate_action_review_path=review, now=_utc("2026-01-02T12:00:00"))["stale_adjustment_basis"] == []


def test_fetch_date_and_scan_date_are_compared_in_ist(database, tmp_path):
    # Fetch 2026-01-04T20:00Z is 2026-01-05 01:30 IST and the scan at 19:00Z is already 2026-01-05 00:30 IST.
    # Both calendar dates are 01-04 in UTC, where the ex-date 01-05 would not yet have arrived.
    _reacquire(database, "r2", "2026-01-04T20:00:00")
    review = _review(tmp_path, _split("2026-01-05"))
    result = run_feature_scan(CFG, db_path=database, corporate_action_review_path=review, now=_utc("2026-01-04T19:00:00"))
    assert result["acquisition_run_id"] == "r2" and result["stale_adjustment_basis"] == ["AAA"]

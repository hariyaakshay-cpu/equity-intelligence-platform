"""dashboard/health.py: the layer cards, the relationship sentence and the freshness rules F1-F9.

Every case injects `now` (naive IST) and builds its own tmp_path database; nothing reads the real data/ files and
nothing depends on the host clock. Reference calendar: Thu 2026-10-01, Fri 10-02, Sat 10-03, Sun 10-04, Mon 10-05,
Tue 10-06, Wed 10-07, Thu 10-08, Mon 10-12.
"""
import hashlib
import inspect
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from dashboard import health, queries
from equity_intel.persistence import connection, db_path_guard
from equity_intel.tests.test_dashboard_exception_queries import db  # noqa: F401  (fixture)
from equity_intel.tests.test_dashboard_freshness_queries import _add_benchmark, _add_e4_scan
from equity_intel.tests.test_dashboard_snapshot_audit_queries import _make_run, _ro

NOW = datetime(2026, 10, 8, 9, 30, 0)             # Thursday morning: the expected session is Wed 2026-10-07
FILE_INFO = {"name": "data/equity_intel.db", "size_bytes": 12_582_912, "modified_at": "2026-10-07T18:45:00"}


def test_the_reference_calendar_is_what_these_tests_assume():
    assert [date(2026, 10, d).weekday() for d in (1, 2, 3, 4, 5, 6, 7, 8, 12)] == [3, 4, 5, 6, 0, 1, 2, 3, 0]


def _complete(db, run_id, started, *, finished="auto", session="2026-10-07", calendar="auto", source="NSE_INDEX|Nifty 500",
              verification="UNVERIFIED_INDEX_ONLY", symbols=()):
    """A COMPLETE full run with chosen finished / session / calendar values (finished runs are frozen, so the run is
    created RUNNING and completed in one UPDATE, exactly like the scanner)."""
    _make_run(db, run_id, started, symbols, end="RUNNING")
    if finished == "auto":
        finished = (datetime.fromisoformat(started) + timedelta(minutes=30)).isoformat()
    if calendar == "auto":
        calendar = json.dumps([session]) if session else None
    counts = {s: sum(1 for x in symbols if x[1] == s) for s in queries.STATUS_VALUES}
    conn = connection.get_connection(db)
    try:
        conn.execute(
            "UPDATE scan_runs SET status = 'COMPLETE', finished_at = ?, latest_closed_session = ?, calendar_dates_json = ?, "
            "calendar_source = ?, calendar_verification = ?, universe_version = 'u', corporate_action_review_version = 'r', "
            "price_source = 't', benchmark = 'B', requested_symbols = ?, successful_symbols = ?, failed_symbols = ?, "
            "status_counts_json = ?, flag_counts_json = '{}', git_commit = 'g', git_dirty = 0 WHERE run_id = ?",
            (finished, session, calendar, source, verification, len(symbols), len(symbols) - counts["FAILED"], counts["FAILED"],
             json.dumps(counts), run_id))
        conn.commit()
    finally:
        conn.close()


def _panel(db, now=NOW, info=FILE_INFO):
    conn = _ro(db)
    try:
        return health.build(conn, now, info)
    finally:
        conn.close()


def _rows(panel):
    return {r["id"]: r for r in panel["freshness"]}


def _strings(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, str):
        yield value


def _keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v)


# ---------------------------------------------------------------- weekdays and the age rule (pure)

@pytest.mark.parametrize("older, newer, expected", [
    (date(2026, 10, 2), date(2026, 10, 5), 1),        # Fri -> Mon: just Monday
    (date(2026, 10, 1), date(2026, 10, 5), 2),        # Thu -> Mon: Friday and Monday
    (date(2026, 10, 3), date(2026, 10, 5), 1),        # Sat -> Mon
    (date(2026, 10, 3), date(2026, 10, 4), 0),        # Sat -> Sun: no weekday between
    (date(2026, 10, 5), date(2026, 10, 5), 0), (date(2026, 10, 7), date(2026, 10, 5), 0),
    (date(2026, 10, 2), date(2026, 10, 12), 6),         # Mon 5, Tue 6, Wed 7, Thu 8, Fri 9, Mon 12
])
def test_weekdays_after_counts_monday_to_friday_dates_in_the_half_open_range(older, newer, expected):
    assert health.weekdays_after(older, newer) == expected


@pytest.mark.parametrize("now, stored, state, behind", [
    (datetime(2026, 10, 2, 18, 0, 0), "2026-10-02", "OK", 0),                # Friday, exactly at the cutoff: today is expected
    (datetime(2026, 10, 2, 18, 0, 0), "2026-10-01", "WARN", 1),
    (datetime(2026, 10, 2, 17, 59, 59), "2026-10-01", "OK", 0),              # one second before the cutoff: Thursday is expected
    (datetime(2026, 10, 2, 17, 59, 59), "2026-10-02", "UNKNOWN", None),      # a session that cannot have closed yet
    (datetime(2026, 10, 3, 10, 0, 0), "2026-10-02", "OK", 0),                # Saturday
    (datetime(2026, 10, 3, 10, 0, 0), "2026-10-01", "WARN", 1),
    (datetime(2026, 10, 4, 23, 59, 59), "2026-10-02", "OK", 0),              # Sunday night
    (datetime(2026, 10, 5, 6, 0, 0), "2026-10-02", "OK", 0),                 # Monday morning: Friday is still the expected session
    (datetime(2026, 10, 5, 6, 0, 0), "2026-10-01", "WARN", 1),
    (datetime(2026, 10, 5, 17, 59, 59), "2026-10-02", "OK", 0),
    (datetime(2026, 10, 5, 18, 0, 0), "2026-10-02", "WARN", 1),              # Monday at the cutoff: Monday is expected
    (datetime(2026, 10, 5, 18, 0, 0), "2026-10-05", "OK", 0),
    (datetime(2026, 10, 7, 18, 0, 0), "2026-10-05", "WARN", 2),              # a holiday-looking gap: Tue and Wed missing
    (datetime(2026, 10, 12, 10, 0, 0), "2026-10-02", "WARN", 5),             # a week behind
])
def test_judge_session_equal_is_ok_behind_is_warn_and_the_cutoff_and_weekends_are_handled(now, stored, state, behind):
    out = health.judge_session(stored, now)
    assert (out["state"], out["weekdays_behind"]) == (state, behind)
    assert out["expected"] == queries.expected_latest_session(now).isoformat()
    if state == "WARN":
        assert health.HOLIDAY_CAVEAT in out["text"] and "market holidays" in out["text"]       # the caveat is always attached
        assert f"{behind} weekday(s) behind" in out["text"]


@pytest.mark.parametrize("stored", [None, "", "garbage", "2026-13-45", "20261001", "2026-10-1", 20261001, "2026-10-01T00:00:00"])
def test_a_missing_null_or_unparseable_date_is_unknown_never_a_guess(stored):
    out = health.judge_session(stored, NOW)
    assert out["state"] == "UNKNOWN" and out["weekdays_behind"] is None and out["date"] is None
    assert "WARN" not in out["state"] and health.HOLIDAY_CAVEAT not in out["text"]


def test_an_over_long_stored_value_is_shortened_in_the_text():
    assert len(health.judge_session("x" * 500, NOW)["text"]) < 120


def test_format_age_and_naive_ist():
    assert health.format_age(timedelta(days=2, hours=3, minutes=5)) == "2d 3h" and health.format_age(timedelta(hours=5, minutes=7)) == "5h 7m"
    assert health.format_age(timedelta(seconds=-1)) is None
    aware = datetime(2026, 10, 1, 20, 0, 0, tzinfo=timezone.utc)
    assert health.naive_ist(aware) == datetime(2026, 10, 2, 1, 30, 0) and health.naive_ist(NOW) == NOW


# ---------------------------------------------------------------- relationship sentence (pure)

def test_relationship_equal_older_newer_and_missing():
    equal = health.relationship("2026-10-01", "2026-10-01", "r1", "acq-1", [], False)
    assert equal["state"] == "equal" and "Both layers are as of 2026-10-01" in equal["sentence"] and "does not reconcile" in equal["sentence"]
    assert "scan run r1" in equal["sentence"] and "acquisition run acq-1" in equal["sentence"] and equal["counts_sentence"] is None
    older = health.relationship("2026-10-05", "2026-10-01", "r1", "acq-1", [], True)
    assert older["state"] == "e4_older" and (older["calendar_days"], older["weekdays"]) == (4, 2)
    assert "4 calendar day(s) (2 weekday(s); weekdays ignore market holidays) older than the ScanRun's latest closed session 2026-10-05" in older["sentence"]
    assert older["sentence"].startswith("The E4 as-of date 2026-10-01") and "describe different sessions" in older["sentence"]
    assert "status counts differ" in older["counts_sentence"] and "does not reconcile" in older["counts_sentence"]
    newer = health.relationship("2026-10-01", "2026-10-05", "r1", "acq-1", [], None)
    assert newer["state"] == "e4_newer" and newer["sentence"].startswith("The ScanRun's latest closed session 2026-10-01")
    assert "older than the E4 as-of date 2026-10-05" in newer["sentence"] and newer["counts_sentence"] is None
    missing = health.relationship(None, "2026-10-01", None, "acq-1", ["there is no COMPLETE full ScanRun"], None)
    assert missing["state"] == "missing" and "cannot be compared by date: there is no COMPLETE full ScanRun" in missing["sentence"]
    assert all("weekdays" in r["basis"].lower() and "ignore market holidays" in r["basis"] for r in (equal, older, newer, missing))


# ---------------------------------------------------------------- F8 and F9 (pure)

@pytest.mark.parametrize("value", ["UNVERIFIED_INDEX_ONLY", "VERIFIED", "PASS", "OK", "PROVISIONAL", None, "", "anything at all", "nse-holiday-file"])
def test_calendar_provenance_is_never_ok_and_shows_the_stored_value(value):
    row = health.calendar_row("F8a", "Calendar provenance", "ScanRun", [("calendar_verification", value)])
    assert row["state"] == "UNKNOWN" and row["state"] != "OK"
    assert (str(value) in row["value"]) if value else ("not recorded" in row["value"])
    assert "PASS" not in row["state"] and "Never OK" in row["rule"]
    assert bool(row["detail"]) == (value == "UNVERIFIED_INDEX_ONLY")


@pytest.mark.parametrize("name", ["C:\\Users\\Akshay\\Equity - intraday\\data\\equity_intel.db", "C:/data/x.db", "/home/x/data/x.db", "\\\\server\\share\\x.db",
                                  "..\\x.db", "data/../x.db", "file:///x.db", "D:rel.db", "", None, 5, "x" * 201])
def test_an_absolute_or_unsafe_database_name_is_never_echoed(name):
    row = health._f9({"name": name, "size_bytes": 10, "modified_at": "2026-10-07T18:45:00"})
    assert row["state"] == "UNKNOWN" and "file name unavailable" in row["value"]
    text = json.dumps(row)
    assert "Users" not in text and "C:" not in text and "/home" not in text and "server" not in text and ".." not in text


def test_f9_shows_the_relative_name_size_and_last_modified_when_all_are_known():
    row = health._f9(FILE_INFO)
    assert row["state"] == "OK" and row["value"] == "data/equity_intel.db, 12,582,912 bytes (12.0 MB), last modified 2026-10-07T18:45:00 IST"
    assert f"schema version {health.SCHEMA_VERSION}" in row["detail"][0]
    assert health._f9({**FILE_INFO, "name": "data\\equity_intel.db"})["value"].startswith("data/equity_intel.db")      # backslashes become slashes


@pytest.mark.parametrize("info", [
    None, {}, {"name": "data/x.db"}, {**FILE_INFO, "size_bytes": None}, {**FILE_INFO, "size_bytes": -1}, {**FILE_INFO, "size_bytes": True},
    {**FILE_INFO, "size_bytes": "12"}, {**FILE_INFO, "modified_at": None}, {**FILE_INFO, "modified_at": "garbage"},
])
def test_f9_is_unknown_when_a_size_or_time_is_missing_or_invalid(info):
    row = health._f9(info)
    assert row["state"] == "UNKNOWN" and row["state"] in health.STATES


def test_read_db_file_info_gives_a_repo_relative_name_or_just_the_file_name(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    target = data / "equity_intel.db"
    target.write_bytes(b"x" * 2048)
    monkeypatch.setattr(db_path_guard, "REPO_ROOT", tmp_path)
    info = health.read_db_file_info(target)
    assert info["name"] == "data/equity_intel.db" and info["size_bytes"] == 2048
    assert health._f9(info)["state"] == "OK" and queries._ist_datetime(info["modified_at"]) is not None
    elsewhere = tmp_path / "other" / "name.db"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"")
    monkeypatch.setattr(db_path_guard, "REPO_ROOT", tmp_path / "data")
    assert health.read_db_file_info(elsewhere)["name"] == "name.db"                      # outside the repo root: the bare file name
    missing = health.read_db_file_info(tmp_path / "data" / "absent.db")
    assert missing["size_bytes"] is None and missing["modified_at"] is None and health._f9(missing)["state"] == "UNKNOWN"
    assert str(tmp_path) not in json.dumps([info, missing])


# ---------------------------------------------------------------- F1 / F2 / F3 through the builder

def test_f1_f2_f3_are_ok_when_both_layers_are_on_the_expected_session(db):
    _complete(db, "r1", "2026-10-07T19:00:00", session="2026-10-07", symbols=[("AAA", "VALID", [])])
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1)
    rows = _rows(_panel(db))
    assert [rows[i]["state"] for i in ("F1", "F2", "F3")] == ["OK", "OK", "OK"]
    assert rows["F1"]["value"] == "run r1, latest closed session 2026-10-07, age 14h 0m"     # finished 19:30 Wednesday, now 09:30 Thursday
    assert rows["F1"]["expected_session"] == "2026-10-07" and rows["F1"]["weekdays_behind"] == 0


def test_f1_and_f2_warn_with_the_holiday_caveat_when_weekdays_behind(db):
    _complete(db, "r1", "2026-10-05T19:00:00", session="2026-10-05", symbols=[("AAA", "VALID", [])])
    _add_e4_scan(db, "e4-1", "2026-10-02T14:00:00+00:00", asof="2026-10-02", acq="acq-1", quality=["VALID"], features=1)
    rows = _rows(_panel(db))
    assert rows["F1"]["state"] == "WARN" and rows["F1"]["weekdays_behind"] == 2 and health.HOLIDAY_CAVEAT in rows["F1"]["detail"][0]
    assert rows["F2"]["state"] == "WARN" and rows["F2"]["weekdays_behind"] == 3 and health.HOLIDAY_CAVEAT in rows["F2"]["detail"][0]
    assert rows["F3"]["state"] == "WARN"


@pytest.mark.parametrize("session", [None, "", "garbage", "2026-13-45"])
def test_f1_is_unknown_when_the_latest_closed_session_is_null_or_unparseable(db, session):
    _complete(db, "r1", "2026-10-07T19:00:00", session=session, calendar=None, symbols=[("AAA", "VALID", [])])
    panel = _panel(db)
    rows = _rows(panel)
    assert rows["F1"]["state"] == "UNKNOWN" and rows["F3"]["state"] == "UNKNOWN" and rows["F4a"]["state"] == "UNKNOWN"
    assert panel["banners"][0]["kind"] == "UNKNOWN" and panel["banners"][0]["layer"] == "ScanRun"
    assert panel["relationship"]["state"] == "missing"


def test_everything_is_unknown_on_an_empty_database_and_nothing_raises(db):
    panel = _panel(db)
    rows = _rows(panel)
    assert [rows[i]["state"] for i in ("F1", "F2", "F3", "F4a", "F4b", "F7")] == ["UNKNOWN"] * 6
    assert rows["F5"]["state"] == "OK" and rows["F6"]["state"] == "OK"                    # nothing ABORTED or RUNNING: genuinely nothing to warn about
    assert panel["layers"] == {"scanrun": None, "e4": None} and panel["layer_disagreements"] is None
    assert "there is no COMPLETE full ScanRun" in panel["relationship"]["sentence"] and "no COMPLETE E4 scan" in panel["relationship"]["sentence"]
    assert all(r["state"] in health.STATES for r in panel["freshness"])


@pytest.mark.parametrize("bad", [None, "garbage", "2026-13-45", "20261001"])
def test_f2_and_the_e4_banner_are_unknown_for_a_null_or_invalid_as_of_date(db, bad):
    _complete(db, "r1", "2026-10-07T19:00:00", symbols=[("AAA", "VALID", [])])
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof=bad, acq="acq-1", quality=["VALID"], features=1)
    panel = _panel(db)
    assert _rows(panel)["F2"]["state"] == "UNKNOWN" and _rows(panel)["F3"]["state"] == "UNKNOWN"
    assert [b["kind"] for b in panel["banners"] if b["layer"] == "E4"] == ["UNKNOWN"]
    assert panel["layers"]["e4"]["asof_date"] is None and panel["layers"]["e4"]["asof_date_raw"] == bad


def test_now_may_be_utc_aware_and_the_cutoff_boundary_is_applied_in_ist(db):
    _complete(db, "r1", "2026-10-01T19:00:00", session="2026-10-01", symbols=[("AAA", "VALID", [])])
    just_before = datetime(2026, 10, 2, 12, 29, 59, tzinfo=timezone.utc)         # 17:59:59 IST on Friday: Thursday is still expected
    at_cutoff = datetime(2026, 10, 2, 12, 30, 0, tzinfo=timezone.utc)            # 18:00:00 IST: Friday is expected
    assert _rows(_panel(db, just_before))["F1"]["state"] == "OK"
    assert _rows(_panel(db, at_cutoff))["F1"]["state"] == "WARN"
    assert _panel(db, at_cutoff)["now"] == "2026-10-02T18:00:00" == health.naive_ist(at_cutoff).isoformat()
    assert _panel(db, at_cutoff) == _panel(db, datetime(2026, 10, 2, 18, 0, 0))     # aware and naive-IST now give the same panel


def test_utc_aware_e4_timestamps_are_shown_as_naive_ist_in_the_card(db):
    _add_e4_scan(db, "e4-1", "2026-10-07T20:00:00+00:00", completed="2026-10-07T20:05:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1)
    card = _panel(db)["layers"]["e4"]
    assert (card["started_at_ist"], card["completed_at_ist"]) == ("2026-10-08T01:30:00", "2026-10-08T01:35:00")


# ---------------------------------------------------------------- F4: index candles

def test_f4_scanrun_ok_and_warn(db):
    _complete(db, "r-ok", "2026-10-01T19:00:00", session="2026-10-01", calendar=json.dumps(["2026-09-30", "2026-10-01", "2026-10-02"]))
    row = _rows(_panel(db))["F4a"]
    assert row["state"] == "OK" and row["last_candle_date"] == "2026-10-02" and "3 session dates stored" in row["value"]
    assert health.CANDLE_NOTE in row["detail"] and "cannot show whether a newer session exists" in row["detail"][0]
    _complete(db, "r-warn", "2026-10-02T19:00:00", session="2026-10-02", calendar=json.dumps(["2026-09-30", "2026-10-01"]))
    row = _rows(_panel(db))["F4a"]
    assert row["state"] == "WARN" and row["last_candle_date"] == "2026-10-01" and row["own_date"] == "2026-10-02"


@pytest.mark.parametrize("raw", [None, "[]", "bad json", '["2026-10-01", "x"]', '{"a": 1}'])
def test_f4_scanrun_is_unknown_when_the_candle_dates_are_missing_or_unparseable(db, raw):
    _complete(db, "r1", "2026-10-03T19:00:00", session="2026-10-02", calendar=raw)
    row = _rows(_panel(db))["F4a"]
    assert row["state"] == "UNKNOWN" and row["last_candle_date"] is None and health.CANDLE_NOTE in row["detail"]


def test_f4_e4_uses_the_benchmark_key_as_stored_demo_or_real_and_shows_the_worst_of_several(db):
    _complete(db, "r1", "2026-10-07T19:00:00", symbols=[("AAA", "VALID", [])])
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1)
    assert _rows(_panel(db))["F4b"]["state"] == "UNKNOWN" and "no benchmark candles stored" in _rows(_panel(db))["F4b"]["value"]
    _add_benchmark(db, "acq-1", "NSE_INDEX|Nifty 500", ["2026-10-06", "2026-10-07"])
    row = _rows(_panel(db))["F4b"]
    assert row["state"] == "OK" and "NSE_INDEX|Nifty 500: last candle date 2026-10-07" in row["value"] and health.CANDLE_NOTE in row["detail"]
    _add_benchmark(db, "acq-1", "DEMO_INDEX", ["2026-10-02"])
    row = _rows(_panel(db))["F4b"]
    assert row["state"] == "WARN" and "DEMO_INDEX: last candle date 2026-10-02" in row["value"]      # one key behind: the worst is shown


def test_f4_e4_is_unknown_when_a_candle_date_or_the_as_of_date_is_unparseable(db):
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1)
    _add_benchmark(db, "acq-1", "K", ["not-a-date"])
    assert _rows(_panel(db))["F4b"]["state"] == "UNKNOWN"


# ---------------------------------------------------------------- F5: ABORTED runs and the newest-run flag

def test_an_aborted_run_is_never_the_latest_complete_run_and_a_newer_one_is_flagged_without_displacing_it(db):
    _complete(db, "r-complete", "2026-10-06T19:00:00", session="2026-10-06", symbols=[("AAA", "VALID", [])])
    _make_run(db, "r-abort", "2026-10-07T09:00:00", end="ABORTED", abort_reason="AUTH_FAILED")
    panel = _panel(db)
    row = _rows(panel)["F5"]
    assert panel["layers"]["scanrun"]["run_id"] == "r-complete" and "run r-complete" in _rows(panel)["F1"]["value"]
    assert row["state"] == "WARN" and row["newest_run_aborted"]["state"] == "flag" and row["newest_run_aborted"]["run_id"] == "r-abort"
    assert "ABORTED and started after the latest COMPLETE full run r-complete" in row["detail"][0]
    assert (row["full"]["count"], row["smoke"]["count"]) == (1, 0) and row["full"]["runs"][0]["abort_reason"] == "AUTH_FAILED"
    assert queries.get_latest_complete_run(_ro(db))["run_id"] == "r-complete"


def test_an_old_aborted_run_outside_the_window_and_older_than_the_complete_run_is_ok(db):
    _make_run(db, "r-abort", "2026-09-01T09:00:00", end="ABORTED")
    _complete(db, "r-complete", "2026-10-06T19:00:00", session="2026-10-06", symbols=[("AAA", "VALID", [])])
    row = _rows(_panel(db))["F5"]
    assert row["state"] == "OK" and row["newest_run_aborted"]["state"] == "none" and (row["full"]["count"], row["smoke"]["count"]) == (0, 0)


def test_a_newer_aborted_run_outside_the_window_still_warns_through_the_flag(db):
    _complete(db, "r-complete", "2026-08-01T19:00:00", session="2026-08-01", symbols=[("AAA", "VALID", [])])
    _make_run(db, "r-abort", "2026-09-01T09:00:00", end="ABORTED")
    row = _rows(_panel(db))["F5"]
    assert row["state"] == "WARN" and row["full"]["count"] == 0 and row["newest_run_aborted"]["state"] == "flag"


def test_the_seven_day_boundary_through_the_builder(db):
    now = datetime(2026, 10, 8, 12, 0, 0)
    _complete(db, "r-complete", "2026-10-07T19:00:00", session="2026-10-07", symbols=[("AAA", "VALID", [])])
    _make_run(db, "r-out", "2026-10-01T11:59:59", end="ABORTED")
    assert _rows(_panel(db, now))["F5"]["state"] == "OK" and _rows(_panel(db, now))["F5"]["full"]["count"] == 0
    _make_run(db, "r-edge", "2026-10-01T12:00:00", end="ABORTED")                       # exactly 7 days before now: inside
    row = _rows(_panel(db, now))["F5"]
    assert row["state"] == "WARN" and [r["run_id"] for r in row["full"]["runs"]] == ["r-edge"] and row["since"] == "2026-10-01T12:00:00"
    assert row["newest_run_aborted"]["state"] == "none"                                 # the COMPLETE run is newer than the newest ABORTED run


def test_full_and_smoke_aborted_runs_are_counted_separately_in_f5(db):
    _complete(db, "r-complete", "2026-10-07T19:00:00", session="2026-10-07", symbols=[("AAA", "VALID", [])])
    _make_run(db, "r-full", "2026-10-07T20:00:00", end="ABORTED")
    _make_run(db, "r-smoke-1", "2026-10-07T21:00:00", [("AAA", "VALID", [])], end="ABORTED", smoke=json.dumps(["AAA"]))
    _make_run(db, "r-smoke-2", "2026-10-07T22:00:00", [("AAA", "VALID", [])], end="ABORTED", smoke=json.dumps(["AAA"]))
    row = _rows(_panel(db))["F5"]
    assert (row["full"]["count"], row["smoke"]["count"]) == (1, 2)
    assert "full runs ABORTED since 2026-10-01T09:30:00: 1" in row["value"] and "smoke runs ABORTED since 2026-10-01T09:30:00: 2" in row["value"]


def test_f5_is_unknown_when_only_unparseable_start_times_exist(db):
    _complete(db, "r-complete", "2026-10-07T19:00:00", session="2026-10-07", symbols=[("AAA", "VALID", [])])
    _make_run(db, "r-bad", "garbage", end="ABORTED")
    row = _rows(_panel(db))["F5"]
    assert row["state"] == "UNKNOWN" and row["unparseable"] == ["r-bad"] and any("cannot be read" in d for d in row["detail"])


# ---------------------------------------------------------------- F6 and F7

def test_f6_running_older_than_the_existing_threshold_warns_with_a_strict_boundary(db):
    now = datetime(2026, 10, 8, 12, 0, 0)
    _make_run(db, "r-exact", "2026-10-08T11:00:00", end="RUNNING")                       # exactly 1 h: not stale
    assert _rows(_panel(db, now))["F6"]["state"] == "OK"
    _make_run(db, "r-stale", "2026-10-08T10:59:59", end="RUNNING")                       # 1 h 1 s: stale
    row = _rows(_panel(db, now))["F6"]
    assert row["state"] == "WARN" and row["stale_run_ids"] == ["r-stale"] and row["running"] == 2
    for run in queries.get_running_runs(_ro(db)):                                        # the same rule as the existing is_running_stale
        assert queries.is_running_stale({"status": "RUNNING", "started_at": run["started_at"]}, now) == (run["run_id"] in row["stale_run_ids"])


def test_f6_unreadable_start_time_is_unknown_and_a_stale_run_still_wins(db):
    _make_run(db, "r-bad", "garbage", end="RUNNING")
    assert _rows(_panel(db))["F6"]["state"] == "UNKNOWN"
    _make_run(db, "r-stale", "2026-10-08T01:00:00", end="RUNNING")
    assert _rows(_panel(db))["F6"]["state"] == "WARN"


@pytest.mark.parametrize("started, finished, state, seconds", [
    ("2026-10-07T19:00:00", "2026-10-07T19:00:03", "OK", 3),
    ("2026-10-07T19:00:00", "2026-10-07T19:00:00", "OK", 0),
    ("2026-10-07T19:00:00", "2026-10-09T19:00:00", "OK", 172800),            # two days: there is no "too slow" rule
])
def test_f7_reports_the_duration_without_a_too_slow_rule(db, started, finished, state, seconds):
    _complete(db, "r1", started, finished=finished, symbols=[("AAA", "VALID", [])])
    row = _rows(_panel(db))["F7"]
    assert (row["state"], row["seconds"]) == (state, seconds)
    assert 'There is no "too slow" rule' in row["rule"]


@pytest.mark.parametrize("finished, state, text", [
    (None, "WARN", "has no finished time"), ("2026-10-07T18:00:00", "WARN", "before the started time"),
    ("garbage", "UNKNOWN", "not readable"), ("", "WARN", "has no finished time"),
])
def test_f7_flags_missing_inverted_and_unparseable_times(db, finished, state, text):
    _complete(db, "r1", "2026-10-07T19:00:00", finished=finished, symbols=[("AAA", "VALID", [])])
    row = _rows(_panel(db))["F7"]
    assert row["state"] == state and text in row["value"]


# ---------------------------------------------------------------- the layer cards: separate totals, no merging

def _scan_and_e4(db, scan_counts, e4_counts, *, session="2026-10-01", asof="2026-10-01"):
    symbols = [(f"{status[:2]}{i:03d}", status, []) for status, n in scan_counts.items() for i in range(n)]
    _complete(db, "r1", "2026-10-02T09:00:00", session=session, symbols=symbols)
    _add_e4_scan(db, "e4-1", "2026-10-02T10:00:00+00:00", asof=asof, acq="acq-1",
                 quality=[s for s, n in e4_counts.items() for _ in range(n)], features=sum(e4_counts.values()))


def test_each_layer_has_its_own_run_id_as_of_and_denominator_and_the_totals_differ(db):
    _scan_and_e4(db, {"VALID": 5, "INSUFFICIENT_HISTORY": 1}, {"VALID": 8, "INSUFFICIENT_HISTORY": 3})
    layers = _panel(db)["layers"]
    scan, e4 = layers["scanrun"], layers["e4"]
    assert (scan["layer"], scan["run_id"], scan["latest_closed_session"], scan["denominator"]) == ("ScanRun", "r1", "2026-10-01", 6)
    assert (e4["layer"], e4["scan_id"], e4["acquisition_run_id"], e4["asof_date"], e4["denominator"]) == ("E4", "e4-1", "acq-1", "2026-10-01", 11)
    assert scan["status_recount"] == {"VALID": 5, "INSUFFICIENT_HISTORY": 1, "STALE": 0, "FAILED": 0} and scan["status_agreement"]["VALID"] == "agree"
    assert e4["status_counts"] == {"INSUFFICIENT_HISTORY": 3, "VALID": 8} and scan["denominator_text"] != e4["denominator_text"]
    assert "6 symbols evaluated" in scan["denominator_text"] and "11 symbols with an E4 quality result" in e4["denominator_text"]


def test_the_scanrun_card_shows_the_stored_counts_next_to_the_recount_with_agree_and_disagree(db):
    _complete(db, "r1", "2026-10-02T09:00:00", symbols=[("AAA", "VALID", []), ("BBB", "VALID", [])])
    card = _panel(db)["layers"]["scanrun"]
    assert card["status_stored"] == card["status_recount"] and set(card["status_agreement"].values()) == {"agree"}


def test_there_is_no_merged_or_combined_total_anywhere_in_the_panel(db):
    _scan_and_e4(db, {"VALID": 5, "INSUFFICIENT_HISTORY": 1}, {"VALID": 8, "INSUFFICIENT_HISTORY": 3})
    panel = _panel(db)
    keys = set(_keys(panel))
    assert not [k for k in keys if re.search(r"total|combined|merged|overall|grand|sum", k, re.I)], keys
    numbers = [6, 11, 17]                                                                 # 6 + 11 would be the merged figure
    assert 17 not in [v for v in _flatten_numbers(panel)] and all(n in _flatten_numbers(panel) for n in numbers[:2])


def _flatten_numbers(value):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _flatten_numbers(v)
    elif isinstance(value, list):
        for v in value:
            yield from _flatten_numbers(v)


def test_the_real_situation_shape_equal_dates_with_different_counts(db):
    """486 / 14 in the ScanRun and 484 / 16 in E4, both as of 2026-10-01 (the user's observation, as synthetic rows)."""
    _scan_and_e4(db, {"VALID": 486, "INSUFFICIENT_HISTORY": 14}, {"VALID": 484, "INSUFFICIENT_HISTORY": 16})
    panel = _panel(db, datetime(2026, 10, 2, 19, 0, 0))
    rel = panel["relationship"]
    assert rel["state"] == "equal" and "Both layers are as of 2026-10-01" in rel["sentence"] and rel["counts_sentence"]
    assert panel["layers"]["scanrun"]["status_recount"]["VALID"] == 486 and panel["layers"]["e4"]["status_counts"]["VALID"] == 484
    assert (panel["layers"]["scanrun"]["denominator"], panel["layers"]["e4"]["denominator"]) == (500, 500)
    assert _rows(panel)["F3"]["state"] == "OK" and _rows(panel)["F1"]["state"] == "WARN"       # Friday evening: Thursday's session is one weekday behind


def test_e4_older_than_the_scanrun_is_said_in_words_with_the_weekday_basis(db):
    _scan_and_e4(db, {"VALID": 3}, {"VALID": 3}, session="2026-10-05", asof="2026-10-01")
    rel = _panel(db)["relationship"]
    assert rel["state"] == "e4_older" and (rel["calendar_days"], rel["weekdays"]) == (4, 2)
    assert "weekdays ignore market holidays" in rel["sentence"] and "older than the ScanRun's latest closed session 2026-10-05" in rel["sentence"]
    assert rel["counts_sentence"] is None                                                  # the same non-zero counts: nothing to say about a difference


def test_e4_newer_than_the_scanrun_and_the_e4_missing_cases(db):
    _scan_and_e4(db, {"VALID": 3}, {"VALID": 3}, session="2026-10-01", asof="2026-10-05")
    assert _panel(db)["relationship"]["state"] == "e4_newer" and _rows(_panel(db))["F3"]["state"] == "WARN"


def test_e4_missing_leaves_the_scanrun_card_and_says_the_layers_cannot_be_compared(db):
    _complete(db, "r1", "2026-10-02T09:00:00", session="2026-10-01", symbols=[("AAA", "VALID", [])])
    panel = _panel(db)
    assert panel["layers"]["e4"] is None and panel["layers"]["scanrun"]["run_id"] == "r1" and panel["layer_disagreements"] is None
    assert panel["relationship"]["state"] == "missing" and "there is no COMPLETE E4 scan" in panel["relationship"]["sentence"]


def test_the_layer_disagreement_list_has_links_counts_and_the_does_not_explain_sentence(db):
    _complete(db, "r1", "2026-10-02T09:00:00", session="2026-10-01",
              symbols=[("AAA", "VALID", []), ("BBB", "VALID", []), ("A&B", "VALID", []), ("ONLYSCAN", "VALID", [])])
    _add_e4_scan(db, "e4-1", "2026-10-02T10:00:00+00:00", asof="2026-10-01", acq="acq-1")
    conn = connection.connect(db)
    for symbol, status in (("AAA", "VALID"), ("BBB", "INSUFFICIENT_HISTORY"), ("A&B", "INSUFFICIENT_HISTORY"), ("ONLYE4", "VALID")):
        conn.execute("INSERT INTO e4_data_quality_results(scan_id,symbol,status,reason,n_bars,w52_complete,break_date,break_ratio,volume_usable) "
                     "VALUES('e4-1',?,?,NULL,252,1,NULL,NULL,1)", (symbol, status))
    conn.commit()
    conn.close()
    found = _panel(db)["layer_disagreements"]
    assert (found["in_both"], found["different"], found["only_in_scanrun"], found["only_in_e4"]) == (3, 2, 1, 1)
    assert found["sentence"] == "2 of 3 symbols present in both layers have a different status in the two layers. Differences are listed as stored; this page does not explain why."
    assert [(r["symbol"], r["stock_url"]) for r in found["rows"]] == [("A&B", "/equity/stock/A%26B"), ("BBB", "/equity/stock/BBB")]
    assert found["note"].endswith("this page does not explain why.")


# ---------------------------------------------------------------- banners

def test_the_outdated_banner_states_its_basis_for_each_layer_separately(db):
    _scan_and_e4(db, {"VALID": 3}, {"VALID": 3}, session="2026-10-06", asof="2026-10-02")
    panel = _panel(db)
    banners = {b["layer"]: b for b in panel["banners"]}
    assert set(banners) == {"ScanRun", "E4"} and all(b["kind"] == "OUTDATED" for b in banners.values())
    scan, e4 = banners["ScanRun"], banners["E4"]
    assert "the ScanRun latest closed session 2026-10-06" in scan["text"] and "the E4 as-of date 2026-10-02" in e4["text"]
    for banner in (scan, e4):
        assert "expected latest session 2026-10-07" in banner["text"] and "18:00 IST cutoff" in banner["text"]
        assert "now (IST) 2026-10-08 09:30:00" in banner["text"] and "Market holidays are unknown" in banner["text"] and "UNVERIFIED_INDEX_ONLY" in banner["text"]
        assert banner["cutoff_hour_ist"] == 18 and banner["expected"] == "2026-10-07"
    assert (scan["stored"], e4["stored"]) == ("2026-10-06", "2026-10-02")


def test_no_banner_when_a_layer_is_on_the_expected_session(db):
    _scan_and_e4(db, {"VALID": 3}, {"VALID": 3}, session="2026-10-07", asof="2026-10-02")
    assert [b["layer"] for b in _panel(db)["banners"]] == ["E4"]


# ---------------------------------------------------------------- every row: rule, now, vocabulary, hygiene

def test_every_row_shows_its_rule_a_valid_state_and_the_printed_now_on_age_based_rows(db):
    _scan_and_e4(db, {"VALID": 3}, {"VALID": 3})
    _make_run(db, "r-abort", "2026-10-07T09:00:00", end="ABORTED")
    panel = _panel(db)
    assert [r["id"] for r in panel["freshness"]] == ["F1", "F2", "F3", "F4a", "F4b", "F5", "F6", "F7", "F8a", "F8b", "F9"]
    for row in panel["freshness"]:
        assert row["state"] in ("OK", "WARN", "UNKNOWN") and row["rule"] and row["label"] and row["value"]
    for row_id in ("F1", "F2", "F5", "F6"):
        assert _rows(panel)[row_id]["now"] == "now (IST) 2026-10-08 09:30:00" == panel["now_text"]
    assert all(_rows(panel)[i]["now"] is None for i in ("F3", "F4a", "F4b", "F7", "F8a", "F8b", "F9"))
    assert panel["title"] == "Display rules, not scoring" and panel["scoring_status"] == "BLOCKED_B2"
    assert "weekday" in _rows(panel)["F1"]["rule"] and "holidays" in _rows(panel)["F1"]["rule"] and "18:00 IST" in _rows(panel)["F1"]["rule"]


@pytest.mark.parametrize("verification", ["UNVERIFIED_INDEX_ONLY", "VERIFIED", "PASS", "OK", None])
def test_calendar_rows_show_the_stored_values_and_are_never_ok(db, verification):
    _complete(db, "r1", "2026-10-07T19:00:00", source="NSE_INDEX|Nifty 500", verification=verification, symbols=[("AAA", "VALID", [])])
    _add_e4_scan(db, "e4-1", "2026-10-07T14:00:00+00:00", asof="2026-10-07", acq="acq-1", quality=["VALID"], features=1, calendar="PROVISIONAL")
    rows = _rows(_panel(db))
    assert rows["F8a"]["state"] == rows["F8b"]["state"] == "UNKNOWN"
    assert "calendar_source: NSE_INDEX|Nifty 500" in rows["F8a"]["value"]
    assert (f"calendar_verification: {verification}" if verification else "calendar_verification: not recorded") in rows["F8a"]["value"]
    assert "calendar_status: PROVISIONAL" in rows["F8b"]["value"]


def test_the_panel_is_json_serialisable_with_no_absolute_path_secret_or_ranking_wording(db, tmp_path):
    _scan_and_e4(db, {"VALID": 3, "INSUFFICIENT_HISTORY": 1}, {"VALID": 2, "INSUFFICIENT_HISTORY": 2})
    _make_run(db, "r-abort", "2026-10-07T09:00:00", end="ABORTED")
    panel = _panel(db, NOW, health.read_db_file_info(db))
    text = json.dumps(panel)
    assert json.loads(text) == panel
    for forbidden in (str(tmp_path), str(db), "C:\\\\Users", "/Users/", ".env", "UPSTOX", "access_token", "ACCESS_TOKEN", "api_key", "Bearer", "password"):
        assert forbidden not in text, forbidden
    words = " ".join(_strings(panel)).lower()
    assert not re.search(r"\b(score|scores|scored|rank|ranks|ranked|ranking|signal|signals|buy|sell|target|targets|stop-?loss|confidence|"
                         r"top picks?|best|worst|strongest|weakest)\b", words)
    assert "PASS" not in " ".join(_strings(panel)) and all(r["state"] != "PASS" for r in panel["freshness"])
    assert not [k for k in _keys(panel) if re.search(r"score|rank|signal|target|stop_?loss|confidence|chart|pass", k, re.I)]
    assert panel["freshness"][-1]["id"] == "F9" and "equity_intel.db" in panel["freshness"][-1]["value"] and str(tmp_path) not in panel["freshness"][-1]["value"]


# ---------------------------------------------------------------- read-only

def test_build_uses_only_a_read_only_connection_and_leaves_the_file_unchanged(db):
    _scan_and_e4(db, {"VALID": 3}, {"VALID": 3})
    _make_run(db, "r-abort", "2026-10-07T09:00:00", end="ABORTED")
    _make_run(db, "r-run", "2026-10-07T09:00:00", end="RUNNING")
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    conn = _ro(db)
    try:
        health.build(conn, NOW, FILE_INFO)
        for statement in ("CREATE TABLE should_not_exist (x)", "UPDATE scan_runs SET status = 'COMPLETE'", "DELETE FROM e4_scan_runs",
                          "DROP TABLE acquired_benchmark", "INSERT INTO acquired_benchmark VALUES('a','b','c',1,'d','e')"):
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(statement)
    finally:
        conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_the_health_module_imports_no_sqlite3_or_forbidden_modules_and_runs_no_sql_itself():
    source = inspect.getsource(health)
    assert not re.search(r"^\s*(import|from)\s+sqlite3", source, re.M)
    assert "conn.execute" not in source and "cursor(" not in source                       # every SQL statement lives in queries.py
    for forbidden in ("brokers", "paper_engine", "continuous_engine", "core.oms", "core.historical_data", "subprocess", "requests", "urllib.request"):
        assert forbidden not in source, forbidden
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER)\s", source)


# ---------------------------------------------------------------- demo seed shape (derived from nothing but the seed's own constants)

def test_the_demo_database_builds_a_full_panel(tmp_path, monkeypatch):
    from scripts import dashboard_demo_seed as seed
    canonical, demo = tmp_path / "equity_intel.db", tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", canonical)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    seed.seed_demo_database(demo)
    panel = _panel(demo, datetime(2026, 9, 26, 12, 0, 0), health.read_db_file_info(demo))
    assert panel["layers"]["scanrun"]["run_id"] == "r-demo-latest-complete" and panel["layers"]["e4"]["scan_id"] == "demo-e4-1"
    assert panel["layers"]["scanrun"]["denominator"] == len(seed.FAKE_SYMBOLS)
    assert _rows(panel)["F1"]["state"] == "OK"                                           # the demo session is the Friday before this injected now
    assert _rows(panel)["F8a"]["state"] == "UNKNOWN" and "DEMO_INDEX" in _rows(panel)["F4b"]["value"]
    assert _rows(_panel(demo, datetime(2026, 10, 8, 9, 30, 0)))["F1"]["state"] == "WARN"

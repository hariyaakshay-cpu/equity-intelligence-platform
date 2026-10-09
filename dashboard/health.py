"""Layers and freshness: the builder behind the Overview's "Display rules, not scoring" panel.

Two layers are kept apart everywhere: the ScanRun layer (scan_runs / symbol_scan_results) and the E4 layer
(e4_scan_runs / e4_data_quality_results). Each has its own run id, as-of date, counts and denominator; nothing
here adds them, merges them or reconciles them. The only things computed across the layers are the comparison
of the two dates and the list of symbols whose status differs, both labelled as descriptive.

Every freshness row has a state of OK, WARN or UNKNOWN and carries the rule that produced it. These are display
rules, not scoring: nothing here ranks, scores or signals. The trading calendar is UNVERIFIED_INDEX_ONLY, so
"weekdays" ignore market holidays, every age rule says so, and a state that depends on a date that is missing,
NULL or unparseable is UNKNOWN, never a guess. Calendar provenance (F8) is never OK.

The builder is a set of pure functions over an injected `now` (naive IST) plus build(), which only calls the
SELECT-only queries in queries.py on a connection the caller opened read-only. It never imports sqlite3 and
returns plain JSON-serialisable values with no absolute path and no secret.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional
from urllib.parse import quote

from dashboard import queries
from equity_intel.config import IST, SESSION_CUTOFF_IST
from equity_intel.persistence import db_path_guard
from equity_intel.persistence.schema import SCHEMA_VERSION

TITLE = "Display rules, not scoring"
STATES = ("OK", "WARN", "UNKNOWN")
ABORTED_WINDOW = timedelta(days=7)
MAX_SHOWN_TEXT = 60

HOLIDAY_CAVEAT = (
    "Weekdays here ignore market holidays, and the calendar is UNVERIFIED_INDEX_ONLY (no holiday file). "
    "If the missing weekday(s) were market holidays this is expected."
)
WEEKDAY_BASIS = "Weekdays are Monday to Friday and ignore market holidays."
CANDLE_NOTE = (
    "This is the last index candle date stored by one scan or acquisition. It is stored data and cannot show "
    "whether a newer session exists."
)
DISAGREEMENT_NOTE = "Differences are listed as stored; this page does not explain why."
EXPECTED_SESSION_RULE = (
    f"Expected session = the most recent Monday-Friday date whose {SESSION_CUTOFF_IST}:00 IST cutoff has passed "
    "as of the printed now. " + WEEKDAY_BASIS
)

RULES = {
    "F1": ("OK: the latest COMPLETE full run's latest closed session equals the expected session. WARN: it is 1 or more "
           "weekdays behind it. UNKNOWN: there is no COMPLETE full run, the session is NULL or unparseable, or it is later "
           "than the expected session (check the host clock). " + EXPECTED_SESSION_RULE + " The age shown is information only."),
    "F2": ("OK: the latest COMPLETE E4 scan's as-of date equals the expected session. WARN: it is 1 or more weekdays "
           "behind it. UNKNOWN: there is no COMPLETE E4 scan, the as-of date is NULL or unparseable, or it is later than "
           "the expected session. " + EXPECTED_SESSION_RULE),
    "F3": "OK: the E4 as-of date equals the ScanRun's latest closed session. WARN: they differ. UNKNOWN: either is missing, NULL or unparseable.",
    "F4": ("OK: the last stored index candle date is on or after that layer's own latest closed session (ScanRun) or as-of "
           "date (E4). WARN: it is earlier. UNKNOWN: the candle dates or the layer's date are missing, NULL or unparseable. "
           "With several benchmark keys the most severe state is shown (WARN, then UNKNOWN, then OK)."),
    "F5": (f"OK: no ABORTED run started in the {ABORTED_WINDOW.days} days before the printed now, and the newest run overall is not "
           "an ABORTED run newer than the latest COMPLETE full run. WARN: either holds. UNKNOWN: neither holds but a start "
           "time could not be read. Full runs and --symbols smoke runs are counted separately."),
    "F6": (f"OK: no RUNNING run started more than {int(queries.RUNNING_STALE_THRESHOLD.total_seconds() // 3600)} hour(s) before the "
           "printed now. WARN: at least one did. UNKNOWN: no WARN, but a RUNNING run's start time could not be read."),
    "F7": ("OK: started and finished are both present and finished is not before started. WARN: a COMPLETE run has no "
           "finished time, or it is before the start. UNKNOWN: a time is unparseable or there is no COMPLETE full run. "
           "There is no \"too slow\" rule."),
    "F8": ("Never OK. The stored calendar provenance is shown as is; UNVERIFIED_INDEX_ONLY and any other or missing value "
           "is UNKNOWN, because no holiday file is used."),
    "F9": "OK: the file name is repo-relative and its size and last-modified time are known (the schema version already matches). UNKNOWN: any of them is not.",
}


# ---------------------------------------------------------------- pure helpers

def naive_ist(now: datetime) -> datetime:
    """`now` as a naive IST datetime (an aware value is converted to IST first)."""
    if now.tzinfo is not None:
        now = now.astimezone(IST).replace(tzinfo=None)
    return now.replace(microsecond=0)


def now_text(now: datetime) -> str:
    return f"now (IST) {now.strftime('%Y-%m-%d %H:%M:%S')}"


def weekdays_after(older: date, newer: date) -> int:
    """How many Monday-Friday dates d satisfy older < d <= newer (0 when newer is not after older)."""
    count, day = 0, older + timedelta(days=1)
    while day <= newer:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def format_age(delta: timedelta) -> Optional[str]:
    """'Xd Yh' for a day or more, else 'Yh Zm'; None for a negative age."""
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return None
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    return f"{days}d {hours}h" if days else f"{hours}h {rest // 60}m"


def _shown(value) -> str:
    text = str(value)
    return text if len(text) <= MAX_SHOWN_TEXT else text[:MAX_SHOWN_TEXT] + "..."


def judge_session(raw, now: datetime) -> dict:
    """OK / WARN / UNKNOWN for one stored session or as-of date against the expected session at `now`.

    {"state", "stored", "date", "expected", "weekdays_behind", "text"}. Equal is OK; N >= 1 weekdays behind is
    WARN (and the holiday caveat is always attached); NULL, empty, unparseable and later-than-expected are UNKNOWN.
    """
    expected = queries.expected_latest_session(now)
    out = {"state": "UNKNOWN", "stored": raw, "date": None, "expected": expected.isoformat(), "weekdays_behind": None, "text": ""}
    if raw is None or raw == "":
        out["text"] = "not recorded (NULL or empty)"
        return out
    parsed = queries._iso_date_or_none(raw)
    if parsed is None:
        out["text"] = f"not a valid date: {_shown(raw)!r}"
        return out
    day = date.fromisoformat(parsed)
    out["date"] = parsed
    if day == expected:
        out.update(state="OK", weekdays_behind=0, text=f"{parsed} equals the expected session {expected.isoformat()}")
    elif day < expected:
        behind = weekdays_after(day, expected)
        out.update(state="WARN", weekdays_behind=behind,
                   text=f"{parsed} is {behind} weekday(s) behind the expected session {expected.isoformat()}. {HOLIDAY_CAVEAT}")
    else:
        out["text"] = f"{parsed} is later than the expected session {expected.isoformat()}; check the host clock"
    return out


def relationship(scan_date: Optional[str], e4_date: Optional[str], scan_run_id: Optional[str], acquisition_run_id: Optional[str],
                 missing: list, counts_differ: Optional[bool]) -> dict:
    """The words that relate the two layers' dates. `scan_date` / `e4_date` are valid ISO dates or None;
    `missing` lists why one is None. State is equal, e4_older, e4_newer or missing."""
    out = {"state": "missing", "scanrun_date": scan_date, "e4_date": e4_date, "calendar_days": None, "weekdays": None,
           "basis": WEEKDAY_BASIS, "counts_sentence": None, "sentence": ""}
    if scan_date is None or e4_date is None:
        out["sentence"] = "The two layers cannot be compared by date: " + "; ".join(missing) + "."
        return out
    scan_day, e4_day = date.fromisoformat(scan_date), date.fromisoformat(e4_date)
    if scan_day == e4_day:
        out["state"] = "equal"
        out["sentence"] = (f"Both layers are as of {scan_date}. Their counts can still differ; this page does not reconcile them. "
                           f"The ScanRun layer classifies from price snapshots stored by scan run {scan_run_id}, the E4 layer from "
                           f"acquisition run {acquisition_run_id}.")
    else:
        older_is_e4 = e4_day < scan_day
        older, newer = (e4_day, scan_day) if older_is_e4 else (scan_day, e4_day)
        out["calendar_days"], out["weekdays"] = (newer - older).days, weekdays_after(older, newer)
        who, whom = ("E4 as-of date", "ScanRun's latest closed session") if older_is_e4 else ("ScanRun's latest closed session", "E4 as-of date")
        out["state"] = "e4_older" if older_is_e4 else "e4_newer"
        out["sentence"] = (f"The {who} {e4_date if older_is_e4 else scan_date} is {out['calendar_days']} calendar day(s) "
                           f"({out['weekdays']} weekday(s); weekdays ignore market holidays) older than the {whom} "
                           f"{scan_date if older_is_e4 else e4_date}. The two sets of counts describe different sessions.")
    if counts_differ:
        out["counts_sentence"] = "The status counts differ between the two layers (shown on each card); this page does not reconcile them."
    return out


def _most_severe(states: list) -> str:
    if "WARN" in states:
        return "WARN"
    if not states or "UNKNOWN" in states:
        return "UNKNOWN"
    return "OK"


def _row(row_id, label, state, value, rule, *, layer=None, detail=None, now=None, extra=None) -> dict:
    assert state in STATES, state
    row = {"id": row_id, "label": label, "state": state, "layer": layer, "value": value, "detail": detail or [], "rule": rule,
           "now": now}
    row.update(extra or {})
    return row


def _banner(layer: str, what: str, judged: dict, now: datetime) -> Optional[dict]:
    """The OUTDATED / UNKNOWN banner of one layer with its basis, or None when the layer is OK."""
    if judged["state"] == "OK":
        return None
    kind = "OUTDATED" if judged["state"] == "WARN" else "UNKNOWN"
    basis = (f"Compared: {what} {judged['stored'] if judged['stored'] not in (None, '') else '(not recorded)'} with the expected latest "
             f"session {judged['expected']}, the most recent Monday-Friday date whose {SESSION_CUTOFF_IST}:00 IST cutoff has passed as of "
             f"{now_text(now)}. Market holidays are unknown (calendar UNVERIFIED_INDEX_ONLY), so a holiday can make this appear wrongly.")
    return {"layer": layer, "kind": kind, "text": f"{kind} ({layer} layer). {basis}", "compared": what,
            "stored": judged["stored"], "expected": judged["expected"], "cutoff_hour_ist": SESSION_CUTOFF_IST, "now": now.isoformat()}


def calendar_row(row_id: str, label: str, layer: str, values: list) -> dict:
    """F8: calendar provenance as stored. The state is always UNKNOWN: nothing here can verify a calendar, so
    no value, known or not, is ever shown as OK."""
    shown = [f"{name}: {_shown(value) if value not in (None, '') else 'not recorded'}" for name, value in values]
    detail = []
    for name, value in values:
        if value == "UNVERIFIED_INDEX_ONLY":
            detail.append("UNVERIFIED_INDEX_ONLY: sessions come from Nifty 500 index candles only; no holiday file is used.")
    return _row(row_id, label, "UNKNOWN", "; ".join(shown), RULES["F8"], layer=layer, detail=detail)


# ---------------------------------------------------------------- short, safe forms of stored reasons
#
# symbol_scan_results.status_reason and e4_data_quality_results.reason can hold raw exception text (see
# scripts/equity_scan.py:302 and :374, acquisition/runner.py:153 and :161), so the health payload never carries
# them. A reason is mapped to a fixed code only when the WHOLE stored string has exactly the structure of a
# template the scanner writes (re.fullmatch, never a prefix match); the code never contains captured text. Any
# other text, including a known prefix followed by extra text, becomes RECORDED_TEXT_NOT_SHOWN.

RECORDED_TEXT_NOT_SHOWN = "RECORDED_TEXT_NOT_SHOWN"
# Every symbol_acquisition_results.status the acquisition code writes (equity_intel/acquisition/runner.py: :47
# MAPPING_FAILED / REQUEST_FAILED, :103 EXCLUDED, :136 NOT_REQUESTED, :177 NO_DATA / SUCCESS, :190 VALIDATION_FAILED,
# :193 INSUFFICIENT_HISTORY) plus MISSING (equity_intel/features/runner.py:79, no acquisition row at all).
ACQUISITION_STATUSES = ("MAPPING_FAILED", "REQUEST_FAILED", "EXCLUDED", "NOT_REQUESTED", "NO_DATA", "VALIDATION_FAILED",
                        "INSUFFICIENT_HISTORY", "SUCCESS", "MISSING")
_N = r"[0-9]+"
_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_BARS = rf"{_N} (?:post-break )?bars; {_N} required"                                           # features/compute.py:72
_BREAK = rf"possible corporate-action break at bar index {_N}, close ratio {_N}\.[0-9]{{4}}"    # features/compute.py:76
SCANRUN_REASON_PATTERNS = (
    (re.compile(r"no instrument-master match for ISIN [A-Z0-9]{12}"), "NO_INSTRUMENT_MATCH"),                          # scripts/equity_scan.py:280
    (re.compile(r"auth failure \(401\)"), "AUTH_FAILURE"),                                                           # scripts/equity_scan.py:298
    (re.compile(rf"only {_N} valid candle\(s\) in the trailing {_N}-session window \(need {_N}\)"), "TOO_FEW_VALID_CANDLES"),    # classification.py:85
    (re.compile(rf"latest valid candle \((?:{_DATE}|None)\) is older than latest_closed_session \({_DATE}\)"),
     "LATEST_CANDLE_OLDER_THAN_SESSION"),                                                                            # classification.py:98
)
E4_REASON_PATTERNS = (
    (re.compile(r"no observations"), "NO_OBSERVATIONS"),                                                              # features/compute.py:35
    (re.compile(rf"{_N} non-positive or missing price value\(s\)"), "NON_POSITIVE_OR_MISSING_PRICES"),                # features/compute.py:35
    (re.compile(_BARS), "TOO_FEW_BARS"),
    (re.compile(_BREAK), "POSSIBLE_PRICE_BREAK"),
    (re.compile(f"{_BARS}; {_BREAK}"), "TOO_FEW_BARS_AND_POSSIBLE_PRICE_BREAK"),                                      # features/compute.py:77
    (re.compile(rf"last observation {_DATE}, run as-of {_DATE}"), "LAST_OBSERVATION_BEFORE_ASOF"),                    # features/runner.py:100
    *((re.compile(re.escape(f"acquisition {status}")), f"ACQUISITION_{status}") for status in ACQUISITION_STATUSES),    # features/runner.py:81 with no reason
    (re.compile(re.escape("acquisition EXCLUDED: Placeholder excluded by B3 resolution")), "ACQUISITION_EXCLUDED"),    # acquisition/runner.py:103
    (re.compile(rf"acquisition INSUFFICIENT_HISTORY: {_N} observations; {_N} required"), "ACQUISITION_INSUFFICIENT_HISTORY"),  # acquisition/runner.py:194
)


def reason_code(layer: str, text) -> Optional[str]:
    """The fixed code for a stored reason, None for NULL or empty, RECORDED_TEXT_NOT_SHOWN for anything else.
    `layer` is "ScanRun" or "E4". The whole string must match a known template; the code contains no stored text."""
    if layer not in ("ScanRun", "E4"):
        raise ValueError(f"unknown layer: {layer!r}")
    if text is None or text == "":
        return None
    if not isinstance(text, str):
        return RECORDED_TEXT_NOT_SHOWN
    for pattern, code in (SCANRUN_REASON_PATTERNS if layer == "ScanRun" else E4_REASON_PATTERNS):
        if pattern.fullmatch(text):
            return code
    return RECORDED_TEXT_NOT_SHOWN


def reason_fields(prefix: str, layer: str, text) -> dict:
    """{f"{prefix}_reason_code", f"{prefix}_reason_recorded"}: the only form in which a stored reason leaves this module."""
    return {f"{prefix}_reason_code": reason_code(layer, text), f"{prefix}_reason_recorded": text is not None and text != ""}


REASON_TEXT_NOTE = ("Only a short code is shown here, not the recorded text. "
                    "The full recorded text is on this symbol's Stock Detail page.")
ABORT_TEXT_NOTE = ("Only the leading code is shown here, not the rest of the recorded text. "
                   "The full recorded text is in the Audit / Provenance section of the /equity page.")

# scan_runs.abort_reason is written only by scan_run.mark_stale_running_as_interrupted (scan_run.py:79), abort_scan_run
# (:141) and abort_scan_run_if_running (:160). The values passed in are these constants: scan_run.py:26 INTERRUPTED,
# :31 UNEXPECTED_ERROR; scanner/acquisition.py:45 AUTH_FAILED, :51 AUTH_FAILURE; scanner/corporate_actions.py:33
# CORPORATE_ACTION_REVIEW_CSV_INVALID; scanner/trading_calendar.py:29 CALENDAR_INVALID; scanner/instrument_master.py:44
# INSTRUMENT_MASTER_UNAVAILABLE; scanner/instrument_mapping.py:56 INSTRUMENT_MAP_EMPTY (callers: scripts/equity_scan.py
# :156, :216, :228, :230, :235, :242, :293). The column is free text (persistence/schema.py:72), so a value of the form
# "CODE: ExceptionClass: message" is still handled: only the leading code is kept.
ABORT_CODES = ("INTERRUPTED", "UNEXPECTED_ERROR", "AUTH_FAILED", "AUTH_FAILURE", "CORPORATE_ACTION_REVIEW_CSV_INVALID",
               "CALENDAR_INVALID", "INSTRUMENT_MASTER_UNAVAILABLE", "INSTRUMENT_MAP_EMPTY")
_ABORT_LEAD = re.compile(r"([A-Z][A-Z_]*)(?::|\Z)")


def abort_code(text) -> Optional[str]:
    """The leading allow-listed code of a stored abort_reason, None for NULL or empty, RECORDED_TEXT_NOT_SHOWN otherwise.
    The code is taken from ABORT_CODES, never copied from the stored text, and everything after it is dropped."""
    if text is None or text == "":
        return None
    if not isinstance(text, str):
        return RECORDED_TEXT_NOT_SHOWN
    lead = _ABORT_LEAD.match(text)
    if lead and lead.group(1) in ABORT_CODES:
        return ABORT_CODES[ABORT_CODES.index(lead.group(1))]
    return RECORDED_TEXT_NOT_SHOWN


def abort_fields(text) -> dict:
    """{"abort_code", "abort_reason_recorded"}: the only form in which a stored abort_reason leaves this module."""
    return {"abort_code": abort_code(text), "abort_reason_recorded": text is not None and text != ""}


def safe_relative_name(name) -> Optional[str]:
    """`name` with forward slashes when it is a short, relative, drive-less path without '..', else None."""
    if not isinstance(name, str) or not name or len(name) > 200:
        return None
    posix = name.replace("\\", "/")
    if PureWindowsPath(name).drive or PureWindowsPath(name).is_absolute() or posix.startswith("/") or ":" in posix:
        return None
    if ".." in PurePosixPath(posix).parts:
        return None
    return posix


def read_db_file_info(db_path) -> dict:
    """{"name", "size_bytes", "modified_at"} for the database file: the name relative to the repo root (just the
    file name when the file is outside it), the size, and the last-modified time as naive IST text. A stat() only;
    never an absolute path."""
    path = Path(db_path)
    try:
        name = path.resolve().relative_to(db_path_guard.REPO_ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        name = path.name
    try:
        stat = path.stat()
    except OSError:
        return {"name": name, "size_bytes": None, "modified_at": None}
    modified = datetime.fromtimestamp(stat.st_mtime, tz=IST).replace(tzinfo=None, microsecond=0)
    return {"name": name, "size_bytes": stat.st_size, "modified_at": modified.isoformat(timespec="seconds")}


# ---------------------------------------------------------------- the rows

def _f1(run: Optional[dict], now: datetime) -> tuple:
    judged = judge_session(run["latest_closed_session"] if run else None, now)
    if run is None:
        judged["text"] = "there is no COMPLETE full run"
        value = "no COMPLETE full run"
    else:
        finished = queries._ist_datetime(run["finished_at"])
        age = format_age(now - finished) if finished is not None else None
        age_text = (f"age {age}" if age else "age unavailable (finished time missing, unparseable or after the printed now)")
        value = f"run {run['run_id']}, latest closed session {run['latest_closed_session'] or 'not recorded'}, {age_text}"
    return judged, _row("F1", "Latest COMPLETE ScanRun", judged["state"], value, RULES["F1"], layer="ScanRun",
                        detail=[judged["text"]], now=now_text(now),
                        extra={"weekdays_behind": judged["weekdays_behind"], "expected_session": judged["expected"]})


def _f2(e4: Optional[dict], now: datetime) -> tuple:
    judged = judge_session(e4["asof_date_raw"] if e4 else None, now)
    if e4 is None:
        judged["text"] = "there is no COMPLETE E4 scan"
        value = "no COMPLETE E4 scan"
    else:
        value = f"E4 scan {e4['scan_id']}, as-of {e4['asof_date_raw'] if e4['asof_date_raw'] not in (None, '') else 'not recorded'}"
    return judged, _row("F2", "E4 as-of date", judged["state"], value, RULES["F2"], layer="E4", detail=[judged["text"]],
                        now=now_text(now), extra={"weekdays_behind": judged["weekdays_behind"], "expected_session": judged["expected"]})


def _candle_state(last_date: Optional[str], own_date: Optional[str]) -> str:
    if last_date is None or own_date is None:
        return "UNKNOWN"
    return "OK" if last_date >= own_date else "WARN"


def _f4_scanrun(conn, run: Optional[dict]) -> dict:
    if run is None:
        return _row("F4a", "Last index candle date (ScanRun calendar)", "UNKNOWN", "no COMPLETE full run", RULES["F4"], layer="ScanRun",
                    detail=[CANDLE_NOTE])
    calendar = queries.get_calendar_last_date(conn, run["run_id"])
    own = queries._iso_date_or_none(run["latest_closed_session"])
    if calendar is None:  # the run row vanished between the two reads; say so rather than guess
        return _row("F4a", "Last index candle date (ScanRun calendar)", "UNKNOWN",
                    f"calendar dates could not be read: run {run['run_id']} was not found; latest closed session {own or 'not recorded'}",
                    RULES["F4"], layer="ScanRun", detail=[CANDLE_NOTE], extra={"last_candle_date": None, "own_date": own})
    last = calendar["last_date"]
    state = _candle_state(last, own)
    if calendar["state"] == "ok":
        value = f"last candle date {last} ({calendar['sessions']} session dates stored); latest closed session {own or 'not recorded'}"
    else:
        value = f"candle dates {calendar['state']} in scan_runs.calendar_dates_json; latest closed session {own or 'not recorded'}"
    return _row("F4a", "Last index candle date (ScanRun calendar)", state, value, RULES["F4"], layer="ScanRun", detail=[CANDLE_NOTE],
                extra={"last_candle_date": last, "own_date": own})


def _f4_e4(conn, e4: Optional[dict]) -> dict:
    label = "Last index candle date (E4 benchmark)"
    if e4 is None:
        return _row("F4b", label, "UNKNOWN", "no COMPLETE E4 scan", RULES["F4"], layer="E4", detail=[CANDLE_NOTE])
    entries = queries.get_benchmark_last_dates(conn, e4["acquisition_run_id"])
    own = e4["asof_date"]
    if not entries:
        return _row("F4b", label, "UNKNOWN", f"no benchmark candles stored for acquisition run {e4['acquisition_run_id']}", RULES["F4"],
                    layer="E4", detail=[CANDLE_NOTE], extra={"benchmarks": [], "own_date": own})
    states = [_candle_state(e["last_date"], own) for e in entries]
    value = "; ".join(f"{e['benchmark_key']}: last candle date {e['last_date'] or 'unparseable'} ({e['sessions']} session dates)"
                      for e in entries) + f"; E4 as-of {own or 'not recorded'}"
    return _row("F4b", label, _most_severe(states), value, RULES["F4"], layer="E4", detail=[CANDLE_NOTE],
                extra={"benchmarks": entries, "own_date": own})


def _newest_aborted_flag(conn, latest: Optional[dict]) -> dict:
    """Is the newest run overall an ABORTED run that started after the latest COMPLETE full run?"""
    newest = queries.get_ineligible_runs(conn, limit=1)["runs"]
    if not newest or newest[0]["kind"] != "ABORTED":
        return {"state": "none", "run_id": None, "text": "the newest ineligible run is not ABORTED, or there is none"}
    run = newest[0]
    if latest is None:
        return {"state": "flag", "run_id": run["run_id"], "text": f"newest ineligible run {run['run_id']} is ABORTED and there is no COMPLETE full run"}
    aborted_at, complete_at = queries._ist_datetime(run["started_at"]), queries._ist_datetime(latest["started_at"])
    if aborted_at is None or complete_at is None:
        return {"state": "unknown", "run_id": run["run_id"], "text": "a start time could not be read, so the order of the runs is unknown"}
    if aborted_at > complete_at:
        return {"state": "flag", "run_id": run["run_id"],
                "text": f"the newest run overall, {run['run_id']}, is ABORTED and started after the latest COMPLETE full run {latest['run_id']}"}
    return {"state": "none", "run_id": run["run_id"], "text": "the latest COMPLETE full run is newer than the newest ABORTED run"}


def _f5(conn, latest: Optional[dict], now: datetime) -> dict:
    cutoff = now - ABORTED_WINDOW
    aborted = queries.get_aborted_runs_since(conn, cutoff)
    flag = _newest_aborted_flag(conn, latest)
    full, smoke = aborted["full"]["count"], aborted["smoke"]["count"]
    if full or smoke or flag["state"] == "flag":
        state = "WARN"
    elif aborted["unparseable"] or flag["state"] == "unknown":
        state = "UNKNOWN"
    else:
        state = "OK"
    detail = [flag["text"]]
    if aborted["unparseable"]:
        detail.append(f"{len(aborted['unparseable'])} ABORTED run(s) have a start time that cannot be read and are not counted: "
                      + ", ".join(aborted["unparseable"][:10]))
    value = (f"full runs ABORTED since {aborted['cutoff']}: {full}; --symbols smoke runs ABORTED since {aborted['cutoff']}: {smoke}")
    shown = {kind: {**aborted[kind], "runs": [  # rebuilt, not edited: the raw abort_reason is dropped and only abort_code leaves this module
        {"run_id": run["run_id"], "started_at": run["started_at"], **abort_fields(run["abort_reason"]),
         "abort_reason_note": ABORT_TEXT_NOTE if run["abort_reason"] not in (None, "") else None}
        for run in aborted[kind]["runs"]]} for kind in ("full", "smoke")}
    return _row("F5", "ABORTED runs in the last 7 days", state, value, RULES["F5"], detail=detail, now=now_text(now),
                extra={"since": aborted["cutoff"], "full": shown["full"], "smoke": shown["smoke"],
                       "unparseable": aborted["unparseable"], "newest_run_aborted": flag, "abort_reason_note": ABORT_TEXT_NOTE})


def _f6(conn, now: datetime) -> dict:
    running = queries.get_running_runs(conn)
    stale, unreadable = [], []
    for run in running:
        started = queries._ist_datetime(run["started_at"])
        if started is None:
            unreadable.append(run["run_id"])
        elif (now - started) > queries.RUNNING_STALE_THRESHOLD:
            stale.append(run["run_id"])
    state = "WARN" if stale else ("UNKNOWN" if unreadable else "OK")
    detail = [f"stale: {', '.join(stale)}"] if stale else []
    if unreadable:
        detail.append("start time cannot be read: " + ", ".join(unreadable[:10]))
    return _row("F6", "RUNNING runs", state, f"{len(running)} RUNNING run(s), {len(stale)} started more than the threshold before the printed now",
                RULES["F6"], detail=detail, now=now_text(now), extra={"running": len(running), "stale_run_ids": stale})


def _f7(run: Optional[dict]) -> dict:
    label = "Latest COMPLETE run duration"
    if run is None:
        return _row("F7", label, "UNKNOWN", "no COMPLETE full run", RULES["F7"], layer="ScanRun")
    started, finished = queries._ist_datetime(run["started_at"]), queries._ist_datetime(run["finished_at"])
    if started is None:
        return _row("F7", label, "UNKNOWN", f"started time not readable ({_shown(run['started_at'])!r})", RULES["F7"], layer="ScanRun")
    if run["finished_at"] in (None, ""):
        return _row("F7", label, "WARN", "a COMPLETE run has no finished time", RULES["F7"], layer="ScanRun")
    if finished is None:
        return _row("F7", label, "UNKNOWN", f"finished time not readable ({_shown(run['finished_at'])!r})", RULES["F7"], layer="ScanRun")
    if finished < started:
        return _row("F7", label, "WARN", "finished time is before the started time", RULES["F7"], layer="ScanRun")
    seconds = int((finished - started).total_seconds())
    return _row("F7", label, "OK", f"run {run['run_id']} took {seconds // 3600}h {seconds % 3600 // 60}m {seconds % 60}s", RULES["F7"],
                layer="ScanRun", extra={"seconds": seconds})


def _f9(info: Optional[dict]) -> dict:
    label = "Database file"
    name = safe_relative_name(info.get("name")) if isinstance(info, dict) else None
    size, modified = (info.get("size_bytes"), info.get("modified_at")) if isinstance(info, dict) else (None, None)
    size_ok = isinstance(size, int) and not isinstance(size, bool) and size >= 0
    modified_dt = queries._ist_datetime(modified)
    if name is None or not size_ok or modified_dt is None:
        parts = [name if name is not None else "file name unavailable",
                 f"{size} bytes" if size_ok else "size unavailable",
                 f"last modified {modified_dt.isoformat(timespec='seconds')} IST" if modified_dt else "last-modified time unavailable"]
        return _row("F9", label, "UNKNOWN", ", ".join(parts), RULES["F9"],
                    detail=[f"schema version {SCHEMA_VERSION} (as expected by this dashboard)"])
    value = f"{name}, {size:,} bytes ({size / 1_048_576:.1f} MB), last modified {modified_dt.isoformat(timespec='seconds')} IST"
    return _row("F9", label, "OK", value, RULES["F9"], detail=[f"schema version {SCHEMA_VERSION} (as expected by this dashboard)"],
                extra={"name": name, "size_bytes": size, "modified_at": modified_dt.isoformat(timespec="seconds")})


# ---------------------------------------------------------------- the layer cards

def _scanrun_card(conn, run: Optional[dict]) -> Optional[dict]:
    if run is None:
        return None
    counts = queries.get_exception_counts(conn, run["run_id"])
    return {
        "layer": "ScanRun", "run_id": run["run_id"], "scan_label": "FULL", "started_at": run["started_at"], "finished_at": run["finished_at"],
        "latest_closed_session": run["latest_closed_session"], "denominator": counts["evaluated"],
        "denominator_text": f"{counts['evaluated']} symbols evaluated by this scan run",
        "status_recount": counts["recount"]["status"], "status_stored": counts["stored"]["status"],
        "status_agreement": counts["agreement"]["status"],
    }


def _e4_card(conn, e4: Optional[dict]) -> Optional[dict]:
    if e4 is None:
        return None
    counts = queries.get_e4_status_counts(conn, e4["scan_id"]) or {"total": 0, "counts": {}, "feature_sets": None}
    return {
        "layer": "E4", "scan_id": e4["scan_id"], "acquisition_run_id": e4["acquisition_run_id"], "asof_date": e4["asof_date"],
        "asof_date_raw": e4["asof_date_raw"], "calendar_status": e4["calendar_status"], "started_at_ist": e4["started_at_ist"],
        "completed_at_ist": e4["completed_at_ist"], "denominator": counts["total"],
        "denominator_text": f"{counts['total']} symbols with an E4 quality result", "status_counts": counts["counts"],
        "feature_sets": counts["feature_sets"],
    }


def _counts_differ(scan_card: Optional[dict], e4_card: Optional[dict]) -> Optional[bool]:
    """Do the two layers' non-zero status counts differ? Compared as stored, status name by status name."""
    if scan_card is None or e4_card is None:
        return None
    scan = {k: v for k, v in scan_card["status_recount"].items() if v}
    e4 = {k: v for k, v in e4_card["status_counts"].items() if v}
    return scan != e4


# ---------------------------------------------------------------- the panel

def build(conn, now: datetime, db_file_info: Optional[dict] = None) -> dict:
    """The whole panel for `now` (naive IST). `db_file_info` is {"name", "size_bytes", "modified_at"} from
    read_db_file_info (or any dict a test passes); it is validated and an absolute path is never echoed."""
    now = naive_ist(now)
    latest = queries.get_latest_complete_run(conn)
    e4 = queries.get_latest_e4_scan_detail(conn)
    scan_card, e4_card = _scanrun_card(conn, latest), _e4_card(conn, e4)

    f1_judged, f1 = _f1(latest, now)
    f2_judged, f2 = _f2(e4, now)
    scan_date = f1_judged["date"]
    e4_date = e4["asof_date"] if e4 else None
    missing = []
    if latest is None:
        missing.append("there is no COMPLETE full ScanRun")
    elif scan_date is None:
        missing.append("the ScanRun latest closed session is not recorded or not a valid date")
    if e4 is None:
        missing.append("there is no COMPLETE E4 scan")
    elif e4_date is None:
        missing.append("the E4 as-of date is not recorded or not a valid date")
    rel = relationship(scan_date, e4_date, latest["run_id"] if latest else None, e4["acquisition_run_id"] if e4 else None, missing,
                       _counts_differ(scan_card, e4_card))
    f3_state = {"equal": "OK", "e4_older": "WARN", "e4_newer": "WARN", "missing": "UNKNOWN"}[rel["state"]]
    f3 = _row("F3", "E4 as-of date vs ScanRun latest closed session", f3_state,
              f"ScanRun {scan_date or 'not available'}; E4 {e4_date or 'not available'}", RULES["F3"], detail=[rel["sentence"]])

    disagreements = None
    if latest is not None and e4 is not None:
        found = queries.get_layer_status_disagreements(conn, latest["run_id"], e4["scan_id"])
        if found is not None:
            found["sentence"] = (f"{found['different']} of {found['in_both']} symbols present in both layers have a different status "
                                 f"in the two layers. {DISAGREEMENT_NOTE}")
            found["note"] = DISAGREEMENT_NOTE
            found["reason_note"] = REASON_TEXT_NOTE
            found["rows"] = [  # rebuilt, not edited: the raw *_reason texts are dropped here and only their short codes leave this module
                {"symbol": row["symbol"], "company_name": row["company_name"],
                 "scanrun_status": row["scanrun_status"], **reason_fields("scanrun", "ScanRun", row["scanrun_reason"]),
                 "e4_status": row["e4_status"], **reason_fields("e4", "E4", row["e4_reason"]),
                 "reason_note": REASON_TEXT_NOTE if row["scanrun_reason"] not in (None, "") or row["e4_reason"] not in (None, "") else None,
                 "stock_url": f"/equity/stock/{quote(row['symbol'], safe='')}"}
                for row in found["rows"]
            ]
        disagreements = found

    rows = [
        f1, f2, f3, _f4_scanrun(conn, latest), _f4_e4(conn, e4), _f5(conn, latest, now), _f6(conn, now), _f7(latest),
        calendar_row("F8a", "Calendar provenance (ScanRun)", "ScanRun",
                     [("calendar_source", latest["calendar_source"] if latest else None),
                      ("calendar_verification", latest["calendar_verification"] if latest else None)]),
        calendar_row("F8b", "Calendar provenance (E4)", "E4", [("calendar_status", e4["calendar_status"] if e4 else None)]),
        _f9(db_file_info),
    ]
    banners = [b for b in (_banner("ScanRun", "the ScanRun latest closed session", f1_judged, now),
                           _banner("E4", "the E4 as-of date", f2_judged, now)) if b]
    return {
        "title": TITLE, "scoring_status": "BLOCKED_B2", "now": now.isoformat(), "now_text": now_text(now),
        "holiday_caveat": HOLIDAY_CAVEAT, "expected_session": f1_judged["expected"], "session_cutoff_hour_ist": SESSION_CUTOFF_IST,
        "layers": {"scanrun": scan_card, "e4": e4_card}, "relationship": rel, "layer_disagreements": disagreements,
        "banners": banners, "freshness": rows,
    }

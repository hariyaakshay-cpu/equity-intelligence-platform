"""Read-only SQL queries backing the dashboard's four sections.

Every function here takes an already-open sqlite3 connection (the caller
is responsible for opening it via
equity_intel.persistence.connection.get_read_only_connection and closing
it) and only ever executes SELECT statements -- this module contains no
INSERT/UPDATE/DELETE anywhere.
"""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from equity_intel.config import SESSION_CUTOFF_IST

IST = timezone(timedelta(hours=5, minutes=30))

# A RUNNING run older than this gets a display-only staleness warning.
RUNNING_STALE_THRESHOLD = timedelta(hours=1)

STATUS_VALUES = ("VALID", "INSUFFICIENT_HISTORY", "STALE", "FAILED")

FLAG_COLUMNS = {
    "history_gaps": "history_gaps_flag",
    "corporate_action_review": "corporate_action_review_flag",
    "price_break_detected": "price_break_detected_flag",
    "non_eq_series": "non_eq_series_flag",
}

_JSON_COLUMNS = (
    "status_counts_json",
    "flag_counts_json",
    "excluded_symbols_json",
    "errors_json",
    "calendar_dates_json",
    "symbols_filter_json",
)


def now_ist_naive() -> datetime:
    """The current time in IST, as a naive datetime.

    scan_runs.started_at/finished_at are written without a UTC offset
    (unlike price_fetch_snapshots.fetched_at_ist, which carries one) --
    see equity_intel/tests/test_schema_constraints.py's fixtures. This
    dashboard treats those naive timestamps as already being IST wall-clock
    time and compares them against this naive "now" rather than mixing
    naive and aware datetimes.
    """
    return datetime.now(timezone.utc).astimezone(IST).replace(tzinfo=None)


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(IST).replace(tzinfo=None)
    return parsed


def _row_to_dict(cursor, row) -> dict:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def _fetch_all_dicts(conn, sql: str, params=()) -> list[dict]:
    cursor = conn.execute(sql, params)
    return [_row_to_dict(cursor, row) for row in cursor.fetchall()]


def _fetch_one_dict(conn, sql: str, params=()) -> Optional[dict]:
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(cursor, row)


def get_latest_complete_run(conn) -> Optional[dict]:
    """The latest COMPLETE run -- excluding a --symbols smoke run.

    A smoke run (symbols_filter_json IS NOT NULL) is a deliberately
    partial run for testing the scanner itself; it must never become
    "the" run the Overview page shows as current, however recent it is.
    """
    return _fetch_one_dict(
        conn,
        "SELECT * FROM scan_runs WHERE status = 'COMPLETE' AND symbols_filter_json IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
    )


def get_run(conn, run_id: str) -> Optional[dict]:
    return _fetch_one_dict(conn, "SELECT * FROM scan_runs WHERE run_id = ?", (run_id,))


def get_previous_complete_run(conn, latest_run: dict) -> Optional[dict]:
    """The COMPLETE full run immediately before `latest_run`, or None.

    Same eligibility as get_latest_complete_run (status COMPLETE, symbols_filter_json
    IS NULL), so ABORTED, RUNNING and --symbols smoke runs are never a baseline. The
    comparison is strictly `started_at < latest.started_at`: a run with an EQUAL
    started_at is not "previous". Among several eligible runs sharing the same
    started_at, run_id DESC picks one deterministically.
    """
    started_at = latest_run.get("started_at")
    if not started_at:
        return None
    return _fetch_one_dict(
        conn,
        "SELECT * FROM scan_runs WHERE status = 'COMPLETE' AND symbols_filter_json IS NULL "
        "AND started_at < ? ORDER BY started_at DESC, run_id DESC LIMIT 1",
        (started_at,),
    )


def _has_table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


E4_FEATURE_COLUMNS = (
    "ema_short", "ema_medium", "ema_long", "rsi", "roc", "relative_return",
    "relative_volume", "distance_from_high", "atr_percent",
)


def get_latest_e4_scan(conn) -> Optional[dict]:
    """The latest COMPLETE E4 feature scan (e4_* tables), or None if there
    is none or the E4 tables do not exist in this database."""
    if not (_has_table(conn, "e4_scan_runs") and _has_table(conn, "e4_feature_sets")):
        return None
    scan = _fetch_one_dict(
        conn,
        "SELECT scan_id, acquisition_run_id, asof_date, calendar_status, indicator_config_json "
        "FROM e4_scan_runs WHERE status = 'COMPLETE' ORDER BY started_at DESC LIMIT 1",
    )
    if scan is None:
        return None
    scan["config"] = json.loads(scan.pop("indicator_config_json"))
    return scan


def get_e4_features(
    conn, e4_scan_id: str, symbols: list[str], acquisition_run_id: Optional[str] = None
) -> dict[str, dict]:
    """Raw E4 indicator values for `symbols`, keyed by symbol. A symbol with
    no feature row (e.g. FAILED or no stored history) is simply absent;
    missing values stay None and are never defaulted to zero.

    Also returns `window_high` (the high-window high used for the distance)
    and, when `acquisition_run_id` is given and its observations exist, the
    `close` on the feature row's last_date from that acquisition run."""
    if not symbols:
        return {}
    marks = ",".join("?" for _ in symbols)
    columns = ", ".join(f"f.{c}" for c in E4_FEATURE_COLUMNS)
    if acquisition_run_id is not None and _has_table(conn, "acquired_observations"):
        close_sql = (
            "(SELECT MAX(o.close) FROM acquired_observations o "
            "WHERE o.run_id = ? AND o.symbol = f.symbol AND o.trading_date = f.last_date)"
        )
        close_params = [acquisition_run_id]
    else:
        close_sql, close_params = "NULL", []
    rows = _fetch_all_dicts(
        conn,
        f"""
        SELECT f.symbol, f.last_date, {columns}, f.prior_high_long AS window_high,
               {close_sql} AS close, q.break_date, q.break_ratio
        FROM e4_feature_sets f
        LEFT JOIN e4_data_quality_results q ON q.scan_id = f.scan_id AND q.symbol = f.symbol
        WHERE f.scan_id = ? AND f.symbol IN ({marks})
        """,
        [*close_params, e4_scan_id, *symbols],
    )
    return {row.pop("symbol"): row for row in rows}


def expected_latest_session(now: Optional[datetime] = None) -> date:
    """The most recent Mon-Fri calendar date whose SESSION_CUTOFF_IST:00
    IST cutoff has already passed, as of `now`.

    This is a real-calendar-day approximation only -- it does not know
    about market holidays (see is_outdated()'s "approximate" label): a
    holiday reads as an ordinary weekday and is expected to have a session
    like any other.
    """
    now = now or now_ist_naive()
    candidate = now.date()
    while True:
        cutoff = datetime.combine(candidate, time(SESSION_CUTOFF_IST, 0))
        if candidate.weekday() < 5 and cutoff <= now:
            return candidate
        candidate -= timedelta(days=1)


def is_outdated(run: dict, now: Optional[datetime] = None) -> bool:
    """OUTDATED = the run's latest_closed_session is earlier than the
    session we'd expect to already be closed by now (see
    expected_latest_session). Unknown (missing latest_closed_session) is
    treated as outdated -- we can't show freshness we can't confirm.

    This is approximate: market holidays are not known here, so a holiday
    can make a genuinely up-to-date run read as OUTDATED after that
    holiday's cutoff. Callers should label it accordingly, e.g. "OUTDATED
    (approximate: market holidays not known)".
    """
    raw = run.get("latest_closed_session")
    if not raw:
        return True
    session_date = date.fromisoformat(raw)
    return session_date < expected_latest_session(now)


def is_running_stale(run: dict, now: Optional[datetime] = None) -> bool:
    if run.get("status") != "RUNNING":
        return False
    now = now or now_ist_naive()
    started = _parse_timestamp(run.get("started_at"))
    if started is None:
        return False
    return (now - started) > RUNNING_STALE_THRESHOLD


def summarize_run(run: dict) -> dict:
    """Parse a scan_runs row's *_json columns into nested JSON values, and
    add a display-only `scan_label` -- "SMOKE (n symbols)" for a
    --symbols run, "FULL" otherwise -- so Scan History never presents a
    smoke run as if it were an ordinary full-universe scan.
    """
    result = dict(run)
    for json_column in _JSON_COLUMNS:
        raw = result.pop(json_column, None)
        key = json_column[: -len("_json")]
        result[key] = json.loads(raw) if raw else None

    symbols_filter = result.get("symbols_filter")
    result["scan_label"] = f"SMOKE ({len(symbols_filter)} symbols)" if symbols_filter else "FULL"
    return result


# Scanner filters/sort over E4 columns -- whitelisted, never interpolated from user input.
E4_RANGE_FILTERS = {"rsi": "f.rsi", "rvol": "f.relative_volume", "dist": "f.distance_from_high"}
SORT_COLUMNS = {
    "symbol": "s.symbol",
    "company_name": "s.company_name",
    "sector": "s.sector",
    "symbol_data_status": "s.symbol_data_status",
    **{name: f"f.{name}" for name in E4_FEATURE_COLUMNS},
}


def get_candidates(
    conn,
    run_id: str,
    page: int = 1,
    page_size: int = 25,
    q: Optional[str] = None,
    status: Optional[str] = None,
    flag: Optional[str] = None,
    *,
    sector: Optional[str] = None,
    ranges: Optional[dict] = None,
    sort: Optional[str] = None,
    sort_dir: str = "asc",
    e4_scan_id: Optional[str] = None,
    escape_like: bool = False,
):
    """One page of symbol results. `ranges` maps a key of E4_RANGE_FILTERS
    to (lo, hi) (either may be None). Filtering or sorting on an E4 column
    needs `e4_scan_id`; a symbol with no value for a filtered column is
    excluded by that filter (the API reports the filters it applied).
    `escape_like` makes `q` a literal substring: % and _ no longer act as wildcards."""
    ranges = {k: v for k, v in (ranges or {}).items() if v and (v[0] is not None or v[1] is not None)}
    if sort is not None and sort not in SORT_COLUMNS:
        raise ValueError(f"unknown sort column: {sort!r}")
    if sort_dir not in ("asc", "desc"):
        raise ValueError(f"unknown sort direction: {sort_dir!r}")
    needs_e4 = bool(ranges) or (sort is not None and sort in E4_FEATURE_COLUMNS)
    if needs_e4 and e4_scan_id is None:
        raise ValueError("E4 indicator filters/sorting need a COMPLETE E4 indicator scan, and none exists")

    conditions = ["s.scan_run_id = ?"]
    params: list = [run_id]

    if q:
        if escape_like:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("(s.symbol LIKE ? ESCAPE '\\' OR s.company_name LIKE ? ESCAPE '\\')")
            like = f"%{escaped}%"
        else:
            conditions.append("(s.symbol LIKE ? OR s.company_name LIKE ?)")
            like = f"%{q}%"
        params.extend([like, like])
    if status:
        if status not in STATUS_VALUES:
            raise ValueError(f"unknown status filter: {status!r}")
        conditions.append("s.symbol_data_status = ?")
        params.append(status)
    if flag:
        if flag not in FLAG_COLUMNS:
            raise ValueError(f"unknown flag filter: {flag!r}")
        conditions.append(f"s.{FLAG_COLUMNS[flag]} = 1")
    if sector:
        if sector == "UNKNOWN":
            conditions.append("s.sector IS NULL")
        else:
            conditions.append("s.sector = ?")
            params.append(sector)
    for key, (lo, hi) in ranges.items():
        if key not in E4_RANGE_FILTERS:
            raise ValueError(f"unknown range filter: {key!r}")
        column = E4_RANGE_FILTERS[key]
        if lo is not None:
            conditions.append(f"{column} >= ?")
            params.append(lo)
        if hi is not None:
            conditions.append(f"{column} <= ?")
            params.append(hi)

    join = ""
    join_params: list = []
    if e4_scan_id is not None:
        join = "LEFT JOIN e4_feature_sets f ON f.scan_id = ? AND f.symbol = s.symbol"
        join_params = [e4_scan_id]

    where = " AND ".join(conditions)
    total = conn.execute(
        f"SELECT COUNT(*) FROM symbol_scan_results s {join} WHERE {where}", [*join_params, *params]
    ).fetchone()[0]

    if sort is not None:
        column = SORT_COLUMNS[sort]
        direction = "DESC" if sort_dir == "desc" else "ASC"
        order = f"({column} IS NULL), {column} {direction}, s.symbol"
    else:
        order = "s.symbol"

    offset = (page - 1) * page_size
    rows = _fetch_all_dicts(
        conn,
        f"""
        SELECT s.* FROM symbol_scan_results s {join}
        WHERE {where}
        ORDER BY {order}
        LIMIT ? OFFSET ?
        """,
        [*join_params, *params, page_size, offset],
    )
    return total, rows


def get_sectors(conn, run_id: str) -> list[dict]:
    rows = _fetch_all_dicts(
        conn,
        """
        SELECT COALESCE(sector, 'UNKNOWN') AS sector, symbol_data_status, COUNT(*) AS n
        FROM symbol_scan_results
        WHERE scan_run_id = ?
        GROUP BY COALESCE(sector, 'UNKNOWN'), symbol_data_status
        ORDER BY sector
        """,
        (run_id,),
    )
    sectors: dict[str, dict] = {}
    for row in rows:
        sector = sectors.setdefault(
            row["sector"],
            {"sector": row["sector"], "total": 0, "status_counts": {s: 0 for s in STATUS_VALUES}},
        )
        sector["status_counts"][row["symbol_data_status"]] = row["n"]
        sector["total"] += row["n"]
    return list(sectors.values())


def _parse_count_map(raw) -> Optional[dict]:
    """A stored *_counts_json value as {UPPERCASE key: int}, or None when it is NULL,
    not valid JSON, or not an object. A value that is not an integer maps to None, so a
    garbled count is "unavailable", never 0. Keys are upper-cased because the scanner
    stores FAILED/HISTORY_GAPS-style keys while other writers use lower case."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {
        str(key).upper(): (value if isinstance(value, int) and not isinstance(value, bool) else None)
        for key, value in parsed.items()
    }


def _agreement(recount: dict, stored: Optional[dict]) -> dict:
    return {
        key: ("unavailable" if stored is None or stored.get(key) is None
              else ("agree" if stored[key] == value else "disagree"))
        for key, value in recount.items()
    }


def get_exception_counts(conn, run_id: str) -> Optional[dict]:
    """Per-status and per-flag counts of one run, recounted from symbol_scan_results in ONE
    aggregate query, next to the counts the run stored in scan_runs (status_counts_json,
    flag_counts_json) with a per-key agree / disagree / unavailable result. None if the run
    does not exist.

    Flag column names come only from FLAG_COLUMNS and status values are bound parameters.
    Descriptive counts only. `symbols.balanced` (successful + failed == requested) is a display
    check, not enforced by the schema; it is None when any of the three numbers is NULL.
    """
    run = get_run(conn, run_id)
    if run is None:
        return None
    flag_keys = {name.upper(): column for name, column in FLAG_COLUMNS.items()}
    select = ["COUNT(*)"]
    select += ["COALESCE(SUM(CASE WHEN symbol_data_status = ? THEN 1 ELSE 0 END), 0)" for _ in STATUS_VALUES]
    select += [f"COALESCE(SUM({column}), 0)" for column in flag_keys.values()]
    row = conn.execute(
        f"SELECT {', '.join(select)} FROM symbol_scan_results WHERE scan_run_id = ?",
        [*STATUS_VALUES, run_id],
    ).fetchone()
    total = row[0]
    status_recount = dict(zip(STATUS_VALUES, row[1 : 1 + len(STATUS_VALUES)]))
    flag_recount = dict(zip(flag_keys, row[1 + len(STATUS_VALUES) :]))

    status_stored = _parse_count_map(run["status_counts_json"])
    flag_stored = _parse_count_map(run["flag_counts_json"])
    requested, successful, failed = run["requested_symbols"], run["successful_symbols"], run["failed_symbols"]
    return {
        "run_id": run_id,
        "evaluated": total,
        "recount": {"status": status_recount, "flags": flag_recount},
        "stored": {
            "status": None if status_stored is None else {k: status_stored.get(k) for k in status_recount},
            "flags": None if flag_stored is None else {k: flag_stored.get(k) for k in flag_recount},
        },
        "agreement": {
            "status": _agreement(status_recount, status_stored),
            "flags": _agreement(flag_recount, flag_stored),
        },
        "symbols": {
            "requested": requested,
            "successful": successful,
            "failed": failed,
            "balanced": None if None in (requested, successful, failed) else successful + failed == requested,
        },
    }


def get_symbol_result(conn, run_id: str, symbol: str) -> Optional[dict]:
    return _fetch_one_dict(
        conn,
        "SELECT * FROM symbol_scan_results WHERE scan_run_id = ? AND symbol = ?",
        (run_id, symbol),
    )


def get_candles(conn, run_id: str, symbol: str, limit: int = 90) -> list[dict]:
    return _fetch_all_dicts(
        conn,
        """
        SELECT trading_date, source, open, high, low, close, volume, candle_validation_status,
               content_hash, fetched_at_ist
        FROM price_fetch_snapshots
        WHERE scan_run_id = ? AND symbol = ?
        ORDER BY trading_date DESC
        LIMIT ?
        """,
        (run_id, symbol, limit),
    )


def get_fetch_history(conn, symbol: str, limit: int = 20) -> list[dict]:
    return _fetch_all_dicts(
        conn,
        """
        SELECT scan_run_id, trading_date, source, fetched_at_ist,
               candle_validation_status, validation_errors_json
        FROM price_fetch_snapshots
        WHERE symbol = ?
        ORDER BY fetched_at_ist DESC
        LIMIT ?
        """,
        (symbol, limit),
    )


def get_scan_history(conn, page: int = 1, page_size: int = 25):
    total = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
    offset = (page - 1) * page_size
    rows = _fetch_all_dicts(
        conn,
        "SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    return total, rows


# ---------------------------------------------------------------------------
# Snapshot Audit queries (Phase 3): compare the STORED price_fetch_snapshots of two COMPLETE full runs.
#
# Nothing here recomputes a hash: the only hash operation is string equality between two stored
# content_hash values. All SQL is parameterized; the only text interpolated into SQL is taken from the
# whitelists below. One bar is (symbol, trading_date, source); the primary key of price_fetch_snapshots
# is (scan_run_id, symbol, trading_date, source), so looking the same bar up in the other run is an
# index search, never a scan.
# ---------------------------------------------------------------------------

ELIGIBLE_RUN_SQL = "status = 'COMPLETE' AND symbols_filter_json IS NULL"  # same rule as get_latest_complete_run
ELIGIBLE_RUN_LIST_LIMIT = 50
INELIGIBLE_RUN_LIST_LIMIT = 20
REVISION_ROW_CAP = 300
AUDIT_SORT_COLUMNS = {"symbol": "s.symbol", "company_name": "s.company_name", "sector": "s.sector"}
SET_DIFF_VIEWS = ("added", "removed")

_RUN_LIST_COLUMNS = (
    "run_id, started_at, finished_at, status, abort_reason, latest_closed_session, universe_version, "
    "corporate_action_review_version, requested_symbols, successful_symbols, failed_symbols, symbols_filter_json"
)
_STORED_SYMBOLS = "(SELECT COUNT(*) FROM symbol_scan_results s WHERE s.scan_run_id = r.run_id) AS stored_symbols"


def get_eligible_runs(conn, limit: int = ELIGIBLE_RUN_LIST_LIMIT) -> dict:
    """COMPLETE full runs (the only runs a comparison may use), newest first.

    {"total": how many exist, "runs": up to `limit` of them, "more": how many are not listed}. A NULL
    requested / successful / failed count stays None ("unavailable"), never 0.
    """
    limit = max(int(limit), 1)
    total = conn.execute(f"SELECT COUNT(*) FROM scan_runs WHERE {ELIGIBLE_RUN_SQL}").fetchone()[0]
    runs = _fetch_all_dicts(
        conn,
        f"SELECT {_RUN_LIST_COLUMNS}, {_STORED_SYMBOLS} FROM scan_runs r WHERE {ELIGIBLE_RUN_SQL} "
        "ORDER BY started_at DESC, run_id DESC LIMIT ?",
        (limit,),
    )
    for run in runs:
        run.pop("symbols_filter_json", None)
    return {"total": total, "runs": runs, "more": max(total - len(runs), 0)}


def _ineligible_reason(run: dict) -> tuple[str, str]:
    """(kind, reason) for a run that may not be compared: ABORTED, RUNNING, or a COMPLETE --symbols smoke run."""
    if run["status"] == "ABORTED":
        return "ABORTED", f"ABORTED ({run['abort_reason'] or 'no abort reason recorded'})"
    if run["status"] == "RUNNING":
        return "RUNNING", "RUNNING (not finished)"
    try:
        symbols = len(json.loads(run["symbols_filter_json"]))
        return "SMOKE", f"smoke run (--symbols, {symbols} symbols)"
    except (TypeError, ValueError):
        return "SMOKE", "smoke run (--symbols, symbol list unreadable)"


def get_ineligible_runs(conn, limit: int = INELIGIBLE_RUN_LIST_LIMIT) -> dict:
    """ABORTED, RUNNING and COMPLETE smoke runs: listed so they are visible, never usable in a comparison.

    {"total", "runs" (newest `limit`), "more" (how many older ones are not listed)}. Each run carries its
    `kind`, `reason`, `requested_symbols` (None when the run recorded none: "unavailable") and `stored_symbols`
    (the symbol result rows actually stored for it).
    """
    limit = max(int(limit), 1)
    total = conn.execute(f"SELECT COUNT(*) FROM scan_runs WHERE NOT ({ELIGIBLE_RUN_SQL})").fetchone()[0]
    runs = _fetch_all_dicts(
        conn,
        f"SELECT {_RUN_LIST_COLUMNS}, {_STORED_SYMBOLS} FROM scan_runs r WHERE NOT ({ELIGIBLE_RUN_SQL}) "
        "ORDER BY started_at DESC, run_id DESC LIMIT ?",
        (limit,),
    )
    for run in runs:
        run["kind"], run["reason"] = _ineligible_reason(run)
        run.pop("symbols_filter_json", None)
    return {"total": total, "runs": runs, "more": max(total - len(runs), 0)}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_symbol_set_diff(
    conn,
    base_run_id: str,
    other_run_id: str,
    *,
    view: Optional[str] = None,
    q: Optional[str] = None,
    sector: Optional[str] = None,
    sort: str = "symbol",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Which symbols exist in which run. `base` is the older run, `other` the newer.

    counts: symbols in each run, `added` (only in the newer run), `removed` (only in the older run) and
    `in_both`. With view="added" or "removed" the matching symbols are also returned, filtered (`q` is a
    literal substring of symbol or company name; `sector`, "UNKNOWN" meaning none stored), sorted by one
    of AUDIT_SORT_COLUMNS and paginated: {"total", "rows"}. The counts never depend on the filters.
    """
    if view is not None and view not in SET_DIFF_VIEWS:
        raise ValueError(f"unknown view: {view!r}")
    if sort not in AUDIT_SORT_COLUMNS:
        raise ValueError(f"unknown sort column: {sort!r}")
    if sort_dir not in ("asc", "desc"):
        raise ValueError(f"unknown sort direction: {sort_dir!r}")
    params = {"base": base_run_id, "other": other_run_id}
    in_base, in_other, in_both = conn.execute(
        "SELECT (SELECT COUNT(*) FROM symbol_scan_results WHERE scan_run_id = :base), "
        "(SELECT COUNT(*) FROM symbol_scan_results WHERE scan_run_id = :other), "
        "(SELECT COUNT(*) FROM symbol_scan_results o JOIN symbol_scan_results b "
        " ON b.scan_run_id = :base AND b.symbol = o.symbol WHERE o.scan_run_id = :other)",
        params,
    ).fetchone()
    result: dict = {
        "view": view,
        "counts": {"symbols_base": in_base, "symbols_other": in_other, "added": in_other - in_both,
                   "removed": in_base - in_both, "in_both": in_both},
        "total": None,
        "rows": [],
    }
    if view is None:
        return result

    owner, absent_from = ("other", "base") if view == "added" else ("base", "other")
    conditions = [
        "s.scan_run_id = :owner",
        "NOT EXISTS (SELECT 1 FROM symbol_scan_results x WHERE x.scan_run_id = :absent AND x.symbol = s.symbol)",
    ]
    where_params: dict = {"owner": params[owner], "absent": params[absent_from]}
    if q:
        conditions.append("(s.symbol LIKE :like ESCAPE '\\' OR s.company_name LIKE :like ESCAPE '\\')")
        where_params["like"] = f"%{_escape_like(q)}%"
    if sector:
        if sector == "UNKNOWN":
            conditions.append("s.sector IS NULL")
        else:
            conditions.append("s.sector = :sector")
            where_params["sector"] = sector
    where = " AND ".join(conditions)
    column = AUDIT_SORT_COLUMNS[sort]
    direction = "DESC" if sort_dir == "desc" else "ASC"
    result["total"] = conn.execute(f"SELECT COUNT(*) FROM symbol_scan_results s WHERE {where}", where_params).fetchone()[0]
    result["rows"] = _fetch_all_dicts(
        conn,
        f"SELECT s.symbol, s.company_name, s.sector, s.symbol_data_status, s.status_reason "
        f"FROM symbol_scan_results s WHERE {where} "
        f"ORDER BY ({column} IS NULL), {column} {direction}, s.symbol LIMIT :limit OFFSET :offset",
        {**where_params, "limit": page_size, "offset": (page - 1) * page_size},
    )
    return result


# One aggregate join of the two runs, grouped by symbol. `overlap` joins each bar of the newer run to the SAME
# bar (symbol, trading_date, source) of the older run through the primary key and counts those whose stored
# content_hash differs; `bars` counts every stored bar per run and symbol. A bar that exists in only one run is
# never in `overlap`, so it is never counted as differing.
REVISION_SUMMARY_SQL = """
WITH overlap AS (
    SELECT o.symbol AS symbol,
           COUNT(*) AS overlapping,
           SUM(CASE WHEN o.content_hash <> b.content_hash THEN 1 ELSE 0 END) AS differing,
           MIN(CASE WHEN o.content_hash <> b.content_hash THEN o.trading_date END) AS first_differing_date,
           MAX(CASE WHEN o.content_hash <> b.content_hash THEN o.trading_date END) AS last_differing_date
    FROM price_fetch_snapshots o
    JOIN price_fetch_snapshots b
      ON b.scan_run_id = :base AND b.symbol = o.symbol AND b.trading_date = o.trading_date AND b.source = o.source
    WHERE o.scan_run_id = :other
    GROUP BY o.symbol
), bars AS (
    SELECT scan_run_id, symbol, COUNT(*) AS n
    FROM price_fetch_snapshots
    WHERE scan_run_id IN (:base, :other)
    GROUP BY scan_run_id, symbol
)
SELECT n.symbol, n.company_name, n.sector,
       a.symbol_data_status AS base_status, n.symbol_data_status AS other_status,
       COALESCE(bb.n, 0) AS bars_base, COALESCE(bo.n, 0) AS bars_other,
       COALESCE(v.overlapping, 0) AS overlapping, COALESCE(v.differing, 0) AS differing,
       v.first_differing_date, v.last_differing_date
FROM symbol_scan_results n
JOIN symbol_scan_results a ON a.scan_run_id = :base AND a.symbol = n.symbol
LEFT JOIN overlap v ON v.symbol = n.symbol
LEFT JOIN bars bb ON bb.scan_run_id = :base AND bb.symbol = n.symbol
LEFT JOIN bars bo ON bo.scan_run_id = :other AND bo.symbol = n.symbol
WHERE n.scan_run_id = :other
ORDER BY n.symbol
"""


def _not_comparable_reason(row: dict) -> Optional[str]:
    """Why a symbol present in both runs cannot be compared bar by bar, or None when it can."""
    reasons = []
    if row["base_status"] == "FAILED":
        reasons.append("FAILED in the older run")
    if row["other_status"] == "FAILED":
        reasons.append("FAILED in the newer run")
    if row["bars_base"] == 0 and row["base_status"] != "FAILED":
        reasons.append("no stored bars in the older run")
    if row["bars_other"] == 0 and row["other_status"] != "FAILED":
        reasons.append("no stored bars in the newer run")
    return "; ".join(reasons) if reasons else None


def get_revision_summary(conn, base_run_id: str, other_run_id: str) -> dict:
    """Bars whose STORED hash differs between two COMPLETE full runs (`base` older, `other` newer).

    A bar is (symbol, trading_date, source). It counts as "differing" only when the same bar exists in both
    runs with a different stored content_hash. Bars present in one run only are counted separately
    (`only_in_older`, `only_in_newer`). Nothing is recomputed; a difference says the stored bytes differ, not why.

    `symbols` has one row per symbol present in BOTH runs (sorted by symbol), each with its own overlap numbers
    and `not_comparable_reason` (None when comparable). `counts` holds the denominators and totals; bar totals
    cover comparable symbols only (a symbol that is FAILED or has no bars in either run cannot be compared).
    """
    rows = _fetch_all_dicts(conn, REVISION_SUMMARY_SQL, {"base": base_run_id, "other": other_run_id})
    comparable = 0
    totals = {"overlapping_bars": 0, "differing_bars": 0, "only_in_older": 0, "only_in_newer": 0, "symbols_with_differing_bars": 0}
    for row in rows:
        row["not_comparable_reason"] = _not_comparable_reason(row)
        row["comparable"] = row["not_comparable_reason"] is None
        row["only_in_older"] = row["bars_base"] - row["overlapping"]
        row["only_in_newer"] = row["bars_other"] - row["overlapping"]
        if row["comparable"]:
            comparable += 1
            totals["overlapping_bars"] += row["overlapping"]
            totals["differing_bars"] += row["differing"]
            totals["only_in_older"] += row["only_in_older"]
            totals["only_in_newer"] += row["only_in_newer"]
            totals["symbols_with_differing_bars"] += 1 if row["differing"] else 0
    counts = get_symbol_set_diff(conn, base_run_id, other_run_id)["counts"]
    counts.update(totals)
    counts["comparable_symbols"] = comparable
    counts["not_comparable_symbols"] = len(rows) - comparable
    return {"counts": counts, "symbols": rows}


def get_stored_bars(conn, run_id: str, symbol: str) -> list[dict]:
    """Every stored bar of ONE symbol in ONE run (trading_date, source, the five stored values, content_hash),
    oldest first, as stored. The rows the per-symbol stored-row integrity check hashes; nothing is computed here."""
    return _fetch_all_dicts(
        conn,
        "SELECT trading_date, source, open, high, low, close, volume, content_hash FROM price_fetch_snapshots "
        "WHERE scan_run_id = ? AND symbol = ? ORDER BY trading_date, source",
        (run_id, symbol),
    )


def get_symbol_revisions(conn, base_run_id: str, other_run_id: str, symbol: str, limit: int = REVISION_ROW_CAP,
                         newest_first: bool = False) -> dict:
    """One symbol's differing bars with the STORED values of both runs side by side, oldest date first
    (newest first with `newest_first=True`, in which case the cap keeps the newest bars).

    At most REVISION_ROW_CAP (300) bars are returned however large `limit` is: `truncated` says whether
    more exist and `differing` is the real total. `overlapping`, `only_in_older` and `only_in_newer` are the
    denominators for this symbol. No hash is recomputed here.
    """
    order = "ORDER BY o.trading_date DESC, o.source" if newest_first else "ORDER BY o.trading_date, o.source"  # fixed text, never user input
    cap = min(max(int(limit), 1), REVISION_ROW_CAP)
    params = {"base": base_run_id, "other": other_run_id, "symbol": symbol}
    bars_base, bars_other, overlapping, differing = conn.execute(
        "SELECT (SELECT COUNT(*) FROM price_fetch_snapshots WHERE scan_run_id = :base AND symbol = :symbol), "
        "(SELECT COUNT(*) FROM price_fetch_snapshots WHERE scan_run_id = :other AND symbol = :symbol), "
        "COUNT(*), COALESCE(SUM(CASE WHEN o.content_hash <> b.content_hash THEN 1 ELSE 0 END), 0) "
        "FROM price_fetch_snapshots o JOIN price_fetch_snapshots b "
        "ON b.scan_run_id = :base AND b.symbol = o.symbol AND b.trading_date = o.trading_date AND b.source = o.source "
        "WHERE o.scan_run_id = :other AND o.symbol = :symbol",
        params,
    ).fetchone()
    rows = _fetch_all_dicts(
        conn,
        "SELECT o.trading_date, o.source, "
        "b.open AS base_open, b.high AS base_high, b.low AS base_low, b.close AS base_close, b.volume AS base_volume, "
        "b.content_hash AS base_hash, b.candle_validation_status AS base_validation, "
        "o.open AS other_open, o.high AS other_high, o.low AS other_low, o.close AS other_close, o.volume AS other_volume, "
        "o.content_hash AS other_hash, o.candle_validation_status AS other_validation "
        "FROM price_fetch_snapshots o JOIN price_fetch_snapshots b "
        "ON b.scan_run_id = :base AND b.symbol = o.symbol AND b.trading_date = o.trading_date AND b.source = o.source "
        f"WHERE o.scan_run_id = :other AND o.symbol = :symbol AND o.content_hash <> b.content_hash {order} LIMIT :cap",
        {**params, "cap": cap},
    )
    return {
        "symbol": symbol, "overlapping": overlapping, "differing": differing,
        "only_in_older": bars_base - overlapping, "only_in_newer": bars_other - overlapping,
        "rows": rows, "cap": cap, "truncated": differing > len(rows),
    }


# ---------------------------------------------------------------------------
# Phase 4 queries: the inputs of the layer counts and the freshness panel.
#
# SELECT-only and parameterized. Nothing is judged here (no OK / WARN): each function returns what is
# stored, plus whether it could be read. A NULL, empty or unparseable value is reported as missing
# (None) and never replaced by a default. Timestamps: scan_runs.* are naive IST wall-clock text (see
# now_ist_naive); e4_scan_runs.* are UTC-aware text. Both are converted to naive IST by
# _parse_timestamp, so a value from one layer can be compared with a value from the other.
# ---------------------------------------------------------------------------

ABORTED_LIST_LIMIT = 50


def _ist_datetime(value) -> Optional[datetime]:
    """`value` as a naive IST datetime, or None when it is NULL, empty or not a timestamp."""
    try:
        return _parse_timestamp(value)
    except (TypeError, ValueError):
        return None


def _ist_text(value) -> Optional[str]:
    parsed = _ist_datetime(value)
    return None if parsed is None else parsed.isoformat(timespec="seconds")


def _iso_date_or_none(value) -> Optional[str]:
    """`value` when it is an ISO calendar date (YYYY-MM-DD), else None."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat() if len(value) == 10 else None
    except ValueError:
        return None


def get_latest_e4_scan_detail(conn) -> Optional[dict]:
    """The latest COMPLETE E4 scan, the same one get_latest_e4_scan picks (same tables, same status and
    ordering), with what that function leaves out: both timestamps and the acquisition run id.

    `started_at` / `completed_at` are the stored text; `started_at_ist` / `completed_at_ist` are naive IST
    text, None when the stored value is NULL or unparseable. `asof_date` is the stored date when it is a
    valid ISO date, else None; `asof_date_raw` always holds what is stored. None when there is no such scan.
    """
    if not (_has_table(conn, "e4_scan_runs") and _has_table(conn, "e4_feature_sets")):
        return None
    scan = _fetch_one_dict(
        conn,
        "SELECT scan_id, acquisition_run_id, started_at, completed_at, asof_date, calendar_status "
        "FROM e4_scan_runs WHERE status = 'COMPLETE' ORDER BY started_at DESC LIMIT 1",
    )
    if scan is None:
        return None
    scan["asof_date_raw"] = scan["asof_date"]
    scan["asof_date"] = _iso_date_or_none(scan["asof_date"])
    scan["started_at_ist"] = _ist_text(scan["started_at"])
    scan["completed_at_ist"] = _ist_text(scan["completed_at"])
    return scan


def get_e4_status_counts(conn, scan_id: str) -> Optional[dict]:
    """The E4 layer's own status counts for one E4 scan, from e4_data_quality_results.

    {"scan_id", "total", "counts": {status: n}, "feature_sets": n or None}. The statuses are whatever the
    table holds (sorted by name); none is assumed and none is added with a zero. `total` is the number of
    quality rows, the E4 layer's own denominator. None when the table does not exist.
    """
    if not _has_table(conn, "e4_data_quality_results"):
        return None
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM e4_data_quality_results WHERE scan_id = ? GROUP BY status ORDER BY status",
        (scan_id,),
    ).fetchall()
    counts = {status: n for status, n in rows}
    feature_sets = None
    if _has_table(conn, "e4_feature_sets"):
        feature_sets = conn.execute("SELECT COUNT(*) FROM e4_feature_sets WHERE scan_id = ?", (scan_id,)).fetchone()[0]
    return {"scan_id": scan_id, "total": sum(counts.values()), "counts": counts, "feature_sets": feature_sets}


def get_aborted_runs_since(conn, cutoff: datetime) -> dict:
    """ABORTED runs whose started_at is at or after `cutoff` (a naive IST datetime), split into full runs
    and `--symbols` smoke runs (symbols_filter_json NOT NULL), which are never added together.

    The boundary is inclusive: a run that started exactly at `cutoff` counts. started_at is compared as a
    parsed timestamp, not as text, so a run whose started_at cannot be parsed is not silently dropped or
    counted: it is listed in `unparseable`. Each of `full` and `smoke` is {"count", "runs" (newest first,
    at most ABORTED_LIST_LIMIT), "more"}. RUNNING and COMPLETE runs are never included, and nothing here
    makes an ABORTED run the "latest" anything.
    """
    rows = _fetch_all_dicts(
        conn,
        "SELECT run_id, started_at, finished_at, abort_reason, symbols_filter_json FROM scan_runs "
        "WHERE status = ? ORDER BY started_at DESC, run_id DESC",
        ("ABORTED",),
    )
    out = {
        "cutoff": cutoff.isoformat(timespec="seconds"), "aborted_total": len(rows), "unparseable": [],
        "full": {"count": 0, "runs": [], "more": 0}, "smoke": {"count": 0, "runs": [], "more": 0},
    }
    for row in rows:
        started = _ist_datetime(row["started_at"])
        if started is None:
            out["unparseable"].append(row["run_id"])
            continue
        if started < cutoff:
            continue
        bucket = out["smoke" if row["symbols_filter_json"] is not None else "full"]
        bucket["count"] += 1
        if len(bucket["runs"]) < ABORTED_LIST_LIMIT:
            bucket["runs"].append({
                "run_id": row["run_id"], "started_at": started.isoformat(timespec="seconds"),
                "abort_reason": row["abort_reason"],
            })
        else:
            bucket["more"] += 1
    return out


def get_benchmark_last_dates(conn, acquisition_run_id: str) -> Optional[list]:
    """The E4 layer's index candles: one entry per benchmark_key stored for the acquisition run,
    {"benchmark_key", "last_date", "sessions"}, ordered by key. No key is assumed or filtered on: the real
    key is `NSE_INDEX|Nifty 500` and the demo's is `DEMO_INDEX`, and each is returned as stored.

    `last_date` is the newest stored trading_date when it is a valid ISO date, else None. This is stored
    data from one acquisition: it cannot show whether a newer session exists. None when the table does not
    exist; [] when the run has no benchmark rows.
    """
    if not _has_table(conn, "acquired_benchmark"):
        return None
    rows = conn.execute(
        "SELECT benchmark_key, MAX(trading_date), COUNT(DISTINCT trading_date) FROM acquired_benchmark "
        "WHERE run_id = ? GROUP BY benchmark_key ORDER BY benchmark_key",
        (acquisition_run_id,),
    ).fetchall()
    return [{"benchmark_key": key, "last_date": _iso_date_or_none(last), "sessions": n} for key, last, n in rows]


def get_calendar_last_date(conn, run_id: str) -> Optional[dict]:
    """The ScanRun layer's index candles: the newest session date in scan_runs.calendar_dates_json, the
    positive list of Nifty 500 session dates the scan built its calendar from.

    {"state": "ok" | "missing" | "unparseable", "last_date", "sessions"}. "missing" is a NULL / empty column
    or an empty list; "unparseable" is invalid JSON, a value that is not a list, or any item that is not an
    ISO date (the list is never partly trusted). Stored data from one scan: it cannot show whether a newer
    session exists. None when the run does not exist.
    """
    row = _fetch_one_dict(conn, "SELECT calendar_dates_json FROM scan_runs WHERE run_id = ?", (run_id,))
    if row is None:
        return None
    raw = row["calendar_dates_json"]
    if raw is None or raw == "":
        return {"state": "missing", "last_date": None, "sessions": 0}
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return {"state": "unparseable", "last_date": None, "sessions": 0}
    if not isinstance(items, list):
        return {"state": "unparseable", "last_date": None, "sessions": 0}
    if not items:
        return {"state": "missing", "last_date": None, "sessions": 0}
    dates = [_iso_date_or_none(item) for item in items]
    if any(d is None for d in dates):
        return {"state": "unparseable", "last_date": None, "sessions": 0}
    return {"state": "ok", "last_date": max(dates), "sessions": len(set(dates))}


DISAGREEMENT_LIST_LIMIT = 100


def get_running_runs(conn) -> list:
    """Every RUNNING run, ordered by the stored started_at text, newest first: {"run_id", "started_at" (stored text), "started_at_ist" (naive IST
    text, None when unparseable), "smoke" (a --symbols run)}. The caller decides which are stale."""
    rows = _fetch_all_dicts(
        conn,
        "SELECT run_id, started_at, symbols_filter_json FROM scan_runs WHERE status = ? ORDER BY started_at DESC, run_id DESC",
        ("RUNNING",),
    )
    return [{"run_id": r["run_id"], "started_at": r["started_at"], "started_at_ist": _ist_text(r["started_at"]),
             "smoke": r["symbols_filter_json"] is not None} for r in rows]


def get_layer_status_disagreements(conn, scan_run_id: str, e4_scan_id: str, limit: int = DISAGREEMENT_LIST_LIMIT) -> Optional[dict]:
    """Symbols whose status differs between the ScanRun layer (symbol_scan_results.symbol_data_status of one
    run) and the E4 layer (e4_data_quality_results.status of one E4 scan). Status names are compared as stored.

    {"in_both", "different", "rows" (symbol order, at most `limit`), "more", "only_in_scanrun", "only_in_e4"}.
    A symbol present in one layer only is counted separately and is not a "difference". Descriptive: nothing
    here says which layer is right or why they differ. None when the E4 quality table does not exist.
    """
    if not _has_table(conn, "e4_data_quality_results"):
        return None
    limit = max(int(limit), 1)
    join = "FROM symbol_scan_results s JOIN e4_data_quality_results q ON q.scan_id = ? AND q.symbol = s.symbol WHERE s.scan_run_id = ?"
    params = (e4_scan_id, scan_run_id)
    in_both = conn.execute(f"SELECT COUNT(*) {join}", params).fetchone()[0]
    different = conn.execute(f"SELECT COUNT(*) {join} AND s.symbol_data_status <> q.status", params).fetchone()[0]
    rows = _fetch_all_dicts(
        conn,
        "SELECT s.symbol AS symbol, s.company_name AS company_name, s.symbol_data_status AS scanrun_status, "
        "s.status_reason AS scanrun_reason, q.status AS e4_status, q.reason AS e4_reason "
        f"{join} AND s.symbol_data_status <> q.status ORDER BY s.symbol LIMIT ?",
        (*params, limit),
    )
    only_scanrun = conn.execute(
        "SELECT COUNT(*) FROM symbol_scan_results s WHERE s.scan_run_id = ? AND NOT EXISTS "
        "(SELECT 1 FROM e4_data_quality_results q WHERE q.scan_id = ? AND q.symbol = s.symbol)",
        (scan_run_id, e4_scan_id),
    ).fetchone()[0]
    only_e4 = conn.execute(
        "SELECT COUNT(*) FROM e4_data_quality_results q WHERE q.scan_id = ? AND NOT EXISTS "
        "(SELECT 1 FROM symbol_scan_results s WHERE s.scan_run_id = ? AND s.symbol = q.symbol)",
        (e4_scan_id, scan_run_id),
    ).fetchone()[0]
    return {"in_both": in_both, "different": different, "rows": rows, "more": max(different - len(rows), 0),
            "only_in_scanrun": only_scanrun, "only_in_e4": only_e4}

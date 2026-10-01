"""Read-only SQL queries backing the dashboard's four sections.

Every function here takes an already-open sqlite3 connection (the caller
is responsible for opening it via
equity_intel.persistence.connection.get_read_only_connection and closing
it) and only ever executes SELECT statements -- this module contains no
INSERT/UPDATE/DELETE anywhere.
"""
from __future__ import annotations

import json
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


def get_e4_features(conn, e4_scan_id: str, symbols: list[str]) -> dict[str, dict]:
    """Raw E4 indicator values for `symbols`, keyed by symbol. A symbol with
    no feature row (e.g. FAILED or no stored history) is simply absent;
    missing values stay None and are never defaulted to zero."""
    if not symbols:
        return {}
    marks = ",".join("?" for _ in symbols)
    columns = ", ".join(f"f.{c}" for c in E4_FEATURE_COLUMNS)
    rows = _fetch_all_dicts(
        conn,
        f"""
        SELECT f.symbol, f.last_date, {columns}, q.break_date, q.break_ratio
        FROM e4_feature_sets f
        LEFT JOIN e4_data_quality_results q ON q.scan_id = f.scan_id AND q.symbol = f.symbol
        WHERE f.scan_id = ? AND f.symbol IN ({marks})
        """,
        [e4_scan_id, *symbols],
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


def get_candidates(
    conn,
    run_id: str,
    page: int = 1,
    page_size: int = 25,
    q: Optional[str] = None,
    status: Optional[str] = None,
    flag: Optional[str] = None,
):
    conditions = ["scan_run_id = ?"]
    params: list = [run_id]

    if q:
        conditions.append("(symbol LIKE ? OR company_name LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    if status:
        if status not in STATUS_VALUES:
            raise ValueError(f"unknown status filter: {status!r}")
        conditions.append("symbol_data_status = ?")
        params.append(status)
    if flag:
        if flag not in FLAG_COLUMNS:
            raise ValueError(f"unknown flag filter: {flag!r}")
        conditions.append(f"{FLAG_COLUMNS[flag]} = 1")

    where = " AND ".join(conditions)
    total = conn.execute(
        f"SELECT COUNT(*) FROM symbol_scan_results WHERE {where}", params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    rows = _fetch_all_dicts(
        conn,
        f"""
        SELECT * FROM symbol_scan_results
        WHERE {where}
        ORDER BY symbol
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
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
        SELECT trading_date, source, open, high, low, close, volume, candle_validation_status
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

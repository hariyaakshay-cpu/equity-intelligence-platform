"""Seed data/equity_intel_demo.db with fabricated data for the dashboard.

This script deletes and recreates the demo database only -- it is an
allow-list, not a deny-list: the target path must resolve to exactly
db_path_guard.DEMO_DB_PATH, or it is refused untouched. This is stricter
than merely rejecting the canonical path (data/equity_intel.db); it also
refuses any other arbitrary path, so a bug or a bad argument can never
delete a file this script wasn't specifically built to manage. Every row
this script writes goes through the normal scan_run lifecycle (INSERT as
RUNNING, add symbol_scan_results/price_fetch_snapshots while RUNNING, then
UPDATE to COMPLETE/ABORTED) so it exercises the same triggers real scanner
code would, rather than poking rows in through a shortcut the real writer
path could never take.

None of the data below is real: symbols, company names, and figures are
invented for exercising the dashboard's four sections, not sourced from
any market-data vendor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard.queries import expected_latest_session
from equity_intel.persistence import connection, db_path_guard

FAKE_SECTORS = ("IT", "Banking", "Pharma", "Auto", "FMCG", "Energy")

# (symbol, company_name, sector, symbol_data_status, status_reason, flags)
FAKE_SYMBOLS = [
    ("DEMOAAA", "Demo Alpha Industries", "IT", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOAAB", "Demo Bravo Systems", "IT", "VALID", None,
     dict(history_gaps=True, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOAAC", "Demo Charlie Software", "IT", "VALID", None,
     dict(history_gaps=False, corporate_action_review=True, price_break_detected=False, non_eq_series=False)),
    ("DEMOBAA", "Demo Bank of Fiction", "Banking", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=True, non_eq_series=False)),
    ("DEMOBAB", "Demo Trust Financial", "Banking", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOBAC", "Demo Capital Holdings", "Banking", "VALID", None,
     dict(history_gaps=True, corporate_action_review=True, price_break_detected=False, non_eq_series=False)),
    ("DEMOPAA", "Demo Pharma Labs", "Pharma", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOPAB", "Demo Remedy Sciences", "Pharma", "STALE", "no fresh candle in the last 5 sessions",
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOPAC", "Demo Wellness Corp", "Pharma", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=True)),
    ("DEMOAUA", "Demo Motors Ltd", "Auto", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOAUB", "Demo Auto Ancillaries", "Auto", "INSUFFICIENT_HISTORY", "only 41 of 252 required sessions available",
     dict(history_gaps=True, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOAUC", "Demo Wheels Corp", "Auto", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOFAA", "Demo Foods Ltd", "FMCG", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOFAB", "Demo Home Products", "FMCG", "FAILED", "provider returned HTTP 500 for the full window",
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOFAC", "Demo Beverages Co", "FMCG", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOENA", "Demo Energy Corp", "Energy", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOENB", "Demo Power Grid Co", "Energy", "VALID", None,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
    ("DEMOENC", "Demo Solar Industries", "Energy", "STALE", "no fresh candle in the last 5 sessions",
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
]
# Pad up to ~30 symbols by cycling through sectors/statuses with distinct symbols.
_STATUS_CYCLE = ("VALID", "VALID", "VALID", "INSUFFICIENT_HISTORY", "STALE", "FAILED")
_REASON_FOR = {
    "INSUFFICIENT_HISTORY": "only a partial history window is available",
    "STALE": "no fresh candle in the last 5 sessions",
    "FAILED": "provider returned an error for the full window",
    "VALID": None,
}
while len(FAKE_SYMBOLS) < 30:
    i = len(FAKE_SYMBOLS)
    sector = FAKE_SECTORS[i % len(FAKE_SECTORS)]
    status = _STATUS_CYCLE[i % len(_STATUS_CYCLE)]
    FAKE_SYMBOLS.append((
        f"DEMOX{i:02d}",
        f"Demo Extra Co {i}",
        sector,
        status,
        _REASON_FOR[status],
        dict(
            history_gaps=(i % 3 == 0),
            corporate_action_review=(i % 5 == 0),
            price_break_detected=(i % 7 == 0),
            non_eq_series=(i % 11 == 0),
        ),
    ))


class RefusedRealDatabaseError(RuntimeError):
    """Raised when the seed script is asked to target the canonical database."""


def _insert_scan_run(conn, run_id, started_at, **extra):
    columns = ["run_id", "started_at", "status", "scoring_status"] + list(extra.keys())
    placeholders = ", ".join("?" for _ in columns)
    values = [run_id, started_at, "RUNNING", "BLOCKED_B2"] + list(extra.values())
    conn.execute(
        f"INSERT INTO scan_runs ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )


def _insert_symbol_result(conn, run_id, symbol, company_name, sector, status, reason, flags):
    conn.execute(
        """
        INSERT INTO symbol_scan_results
            (scan_run_id, symbol, company_name, sector, symbol_data_status, status_reason,
             available_session_count, missing_session_count,
             history_gaps_flag, corporate_action_review_flag,
             price_break_detected_flag, non_eq_series_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, symbol, company_name, sector, status, reason,
            252 if status != "INSUFFICIENT_HISTORY" else 41,
            0 if status != "INSUFFICIENT_HISTORY" else 211,
            int(flags["history_gaps"]),
            int(flags["corporate_action_review"]),
            int(flags["price_break_detected"]),
            int(flags["non_eq_series"]),
        ),
    )


def _insert_snapshot(conn, run_id, symbol, trading_date, fetched_at_ist, close):
    conn.execute(
        """
        INSERT INTO price_fetch_snapshots
            (scan_run_id, symbol, trading_date, source, fetched_at_ist,
             open, high, low, close, volume, content_hash, candle_validation_status)
        VALUES (?, ?, ?, 'demo-seed', ?, ?, ?, ?, ?, ?, ?, 'VALID')
        """,
        (
            run_id, symbol, trading_date, fetched_at_ist,
            str(close - 1), str(close + 2), str(close - 2), str(close),
            1_000_000,
            f"demo-{symbol}-{trading_date}",
        ),
    )


def _complete_run(
    conn, run_id, finished_at, latest_closed_session, status_counts, flag_counts, requested, successful, failed
):
    conn.execute(
        """
        UPDATE scan_runs
        SET status = 'COMPLETE', finished_at = ?, latest_closed_session = ?,
            universe_version = 'demo-universe-hash', corporate_action_review_version = 'demo-review-hash',
            benchmark = 'NIFTY 50', calendar_source = 'demo-calendar', calendar_verification = 'UNVERIFIED_INDEX_ONLY',
            requested_symbols = ?, successful_symbols = ?, failed_symbols = ?,
            status_counts_json = ?, flag_counts_json = ?, git_commit = 'deadbeefcafe', git_dirty = 0
        WHERE run_id = ?
        """,
        (
            finished_at, latest_closed_session,
            requested, successful, failed,
            json.dumps(status_counts), json.dumps(flag_counts), run_id,
        ),
    )


def _abort_run(conn, run_id, finished_at, abort_reason, errors):
    conn.execute(
        """
        UPDATE scan_runs
        SET status = 'ABORTED', finished_at = ?, abort_reason = ?, errors_json = ?,
            calendar_source = 'demo-calendar', calendar_verification = 'UNVERIFIED_INDEX_ONLY'
        WHERE run_id = ?
        """,
        (finished_at, abort_reason, json.dumps(errors), run_id),
    )


def _status_and_flag_counts(rows):
    status_counts = {"VALID": 0, "INSUFFICIENT_HISTORY": 0, "STALE": 0, "FAILED": 0}
    flag_counts = {
        "history_gaps": 0, "corporate_action_review": 0,
        "price_break_detected": 0, "non_eq_series": 0,
    }
    for _symbol, _name, _sector, status, _reason, flags in rows:
        status_counts[status] += 1
        for flag_name, value in flags.items():
            if value:
                flag_counts[flag_name] += 1
    return status_counts, flag_counts


def seed_demo_database(path: Optional[Path] = None) -> None:
    """Delete and recreate the demo database with fabricated lifecycle data.

    `path` defaults to db_path_guard.DEMO_DB_PATH, looked up dynamically
    (module-qualified, not a name imported directly into this module) so
    that tests monkeypatching db_path_guard.DEMO_DB_PATH still take effect.

    This is an allow-list, not a deny-list: `path` must resolve to exactly
    db_path_guard.DEMO_DB_PATH (not merely "anything but the canonical
    path"). Nothing is touched -- no unlink, no write -- unless that holds.

    Raises:
        RefusedRealDatabaseError: if `path` does not resolve to
            DEMO_DB_PATH. Checked before any file is touched.
    """
    if path is None:
        path = db_path_guard.DEMO_DB_PATH
    resolved = Path(path).resolve(strict=False)
    allowed = db_path_guard.DEMO_DB_PATH.resolve(strict=False)
    if resolved != allowed:
        raise RefusedRealDatabaseError(
            f"dashboard_demo_seed.py only ever writes to the demo database ({allowed}); "
            f"refusing to touch {resolved}"
        )

    if resolved.exists():
        resolved.unlink()

    conn = connection.get_connection(resolved)
    try:
        connection.initialize_schema(conn)
        status_counts, flag_counts = _status_and_flag_counts(FAKE_SYMBOLS)

        # r1: an older COMPLETE run, pinned to a fixed date far in the
        # past -- always OUTDATED, exercising the dashboard's warning
        # regardless of when the demo is seeded or viewed.
        _insert_scan_run(conn, "r-demo-old-complete", "2026-09-01T09:20:00")
        for symbol, name, sector, status, reason, flags in FAKE_SYMBOLS:
            _insert_symbol_result(conn, "r-demo-old-complete", symbol, name, sector, status, reason, flags)
            _insert_snapshot(conn, "r-demo-old-complete", symbol, "2026-09-01", "2026-09-01T09:20:00+05:30", 100.0)
        _complete_run(
            conn, "r-demo-old-complete", "2026-09-01T09:45:00", "2026-09-01",
            status_counts, flag_counts,
            requested=len(FAKE_SYMBOLS),
            successful=status_counts["VALID"],
            failed=status_counts["FAILED"],
        )
        conn.commit()

        # r2: the latest COMPLETE run -- the one the Overview page should
        # show. Its latest_closed_session is computed at seed time (not
        # hardcoded) so a freshly-seeded demo DB is never itself OUTDATED,
        # no matter what day it is seeded on.
        latest_session = expected_latest_session().isoformat()
        _insert_scan_run(conn, "r-demo-latest-complete", "2026-09-27T09:20:00")
        for symbol, name, sector, status, reason, flags in FAKE_SYMBOLS:
            _insert_symbol_result(conn, "r-demo-latest-complete", symbol, name, sector, status, reason, flags)
            _insert_snapshot(
                conn, "r-demo-latest-complete", symbol, "2026-09-26", "2026-09-27T09:20:00+05:30", 101.5
            )
        _complete_run(
            conn, "r-demo-latest-complete", "2026-09-27T09:45:00", latest_session,
            status_counts, flag_counts,
            requested=len(FAKE_SYMBOLS),
            successful=status_counts["VALID"],
            failed=status_counts["FAILED"],
        )
        conn.commit()

        # r3: an ABORTED run with an abort_reason and recorded errors.
        _insert_scan_run(conn, "r-demo-aborted", "2026-09-27T15:10:00")
        _abort_run(
            conn, "r-demo-aborted", "2026-09-27T15:12:00",
            "calendar verification failed: exchange holiday list unavailable",
            ["CalendarSourceUnavailableError: demo-calendar returned HTTP 503"],
        )
        conn.commit()

        # r4: a RUNNING run, started well over an hour ago -- exercises the
        # dashboard's "RUNNING run older than 1 hour" warning regardless of
        # what time of day the demo is viewed.
        _insert_scan_run(conn, "r-demo-running", "2026-09-20T09:15:00")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_demo_database()
    print(f"Seeded demo database at {db_path_guard.DEMO_DB_PATH.resolve(strict=False)}")

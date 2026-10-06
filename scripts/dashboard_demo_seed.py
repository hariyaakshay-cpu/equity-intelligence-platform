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
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from equity_intel.persistence import connection, db_path_guard
from equity_intel.scanner.snapshots import compute_content_hash

FAKE_SECTORS = ("IT", "Banking", "Pharma", "Auto", "FMCG", "Energy")

# Fabricated bar dates shared by the two newest full runs. Weekdays only
# (Wed, Thu, Fri). The demo is deterministic: the newest full run's
# latest_closed_session is the last bar date, so as seeded it reads OUTDATED
# against today's date (it is demo data from September) and, as of that Friday
# evening, current. A STALE demo symbol has no bar on that last date.
BAR_DATES = ("2026-09-23", "2026-09-24", "2026-09-25")
SESSION_DATE = BAR_DATES[-1]
STALE_LAST_DATE = BAR_DATES[-2]
STALE_REASON = f"latest valid candle ({STALE_LAST_DATE}) is older than latest_closed_session ({SESSION_DATE})"

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
    ("DEMOPAB", "Demo Remedy Sciences", "Pharma", "STALE", STALE_REASON,
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
    ("DEMOENC", "Demo Solar Industries", "Energy", "STALE", STALE_REASON,
     dict(history_gaps=False, corporate_action_review=False, price_break_detected=False, non_eq_series=False)),
]
# Pad up to ~30 symbols by cycling through sectors/statuses with distinct symbols.
_STATUS_CYCLE = ("VALID", "VALID", "VALID", "INSUFFICIENT_HISTORY", "STALE", "FAILED")
_REASON_FOR = {
    "INSUFFICIENT_HISTORY": "only a partial history window is available",
    "STALE": STALE_REASON,
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
        # A FAILED symbol was never classified or reviewed, so (as in the real scanner,
        # scripts/equity_scan.py record_failed) only NON_EQ_SERIES can be set on it.
        dict(
            history_gaps=(i % 3 == 0) and status != "FAILED",
            corporate_action_review=(i % 5 == 0) and status != "FAILED",
            price_break_detected=(i % 7 == 0) and status != "FAILED",
            non_eq_series=(i % 11 == 0),
        ),
    ))


# Date whose bars the newest full run revises relative to the previous one.
REVISED_DATE = BAR_DATES[1]
# Equal to the demo E4 config's minimum_history_bars, so a VALID demo symbol
# really has the history its E4 config demands.
E4_DEMO_BARS = 252
DEMO_ADJUSTMENT_STATUS = "DEMO fabricated series (not a real adjustment basis)"
DEMO_E4_CONFIG = {
    "ema_short": 20, "ema_medium": 50, "ema_long": 200, "rsi_period": 14, "roc_lookback": 10,
    "relative_return_lookback": 60, "rvol_window": 20, "high_window": 252, "atr_period": 14,
    "break_low_ratio": 0.5, "break_high_ratio": 2.0, "minimum_history_bars": 252,
    "minimum_universe_count": 450, "volume_usable_bars": 15, "volume_usable_window": 20,
    "label": "demo fabricated, not B2-authoritative",
}


def _bar_dates_for(status: str) -> tuple:
    """Bar dates a symbol has in a full run: a STALE symbol's newest bar is
    older than the run's session, so it lacks the last date; a FAILED symbol
    has none (the real scanner rolls back a failed symbol's snapshots, or never
    fetches it at all when its ISIN is unmapped)."""
    if status == "FAILED":
        return ()
    return BAR_DATES[:-1] if status == "STALE" else BAR_DATES


def _bar_values(index: int, trading_date: str, *, revised: bool) -> tuple[float, int]:
    """DEMO ONLY: synthetic revisions (fabricated), not a model of vendor behaviour.

    (close, volume) for symbol number `index` on `trading_date`. The newest
    run (revised=True) revises some REVISED_DATE bars: a close for every 6th
    symbol, a volume for every 9th, to give the snapshot-audit view real changes."""
    close, volume = 100.0 + index + BAR_DATES.index(trading_date) * 0.5, 1_000_000
    if revised and trading_date == REVISED_DATE:
        if index % 6 == 0:
            close += 0.75
        if index % 9 == 0:
            volume += 12_345
    return close, volume


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
            # FAILED rows store NULL counts, exactly like the real scanner (record_failed)
            None if status == "FAILED" else (252 if status != "INSUFFICIENT_HISTORY" else 41),
            None if status == "FAILED" else (0 if status != "INSUFFICIENT_HISTORY" else 211),
            int(flags["history_gaps"]),
            int(flags["corporate_action_review"]),
            int(flags["price_break_detected"]),
            int(flags["non_eq_series"]),
        ),
    )


def _insert_snapshot(conn, run_id, symbol, trading_date, fetched_at_ist, close, volume=1_000_000):
    """Insert one fabricated bar. The content_hash is the real canonical hash
    of the stored values, so the dashboard's per-symbol hash recomputation
    can be exercised on demo data."""
    prices = [f"{close - 1:.2f}", f"{close + 2:.2f}", f"{close - 2:.2f}", f"{close:.2f}"]
    content_hash = compute_content_hash(trading_date, *prices, volume)
    conn.execute(
        """
        INSERT INTO price_fetch_snapshots
            (scan_run_id, symbol, trading_date, source, fetched_at_ist,
             open, high, low, close, volume, content_hash, candle_validation_status)
        VALUES (?, ?, ?, 'demo-seed', ?, ?, ?, ?, ?, ?, ?, 'VALID')
        """,
        (run_id, symbol, trading_date, fetched_at_ist, *prices, volume, content_hash),
    )


def _complete_run(
    conn, run_id, finished_at, latest_closed_session, status_counts, flag_counts, requested, successful, failed
):
    conn.execute(
        """
        UPDATE scan_runs
        SET status = 'COMPLETE', finished_at = ?, latest_closed_session = ?,
            universe_version = 'demo-universe-hash', corporate_action_review_version = 'demo-review-hash',
            price_source = 'demo-seed', benchmark = 'NIFTY 50', calendar_source = 'demo-calendar', calendar_verification = 'UNVERIFIED_INDEX_ONLY',
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


def _require_demo_path(path) -> Path:
    """The one guard for every writer in this script: `path` must resolve to
    exactly db_path_guard.DEMO_DB_PATH. Stricter than connection.connect()'s
    allow-list, which also admits the canonical data/equity_intel.db.

    DEMO_DB_PATH is looked up dynamically (module-qualified) so tests that
    monkeypatch it still take effect. Raises RefusedRealDatabaseError before
    anything is touched, so callers must invoke this before opening a
    connection or unlinking a file.
    """
    resolved = Path(path).resolve(strict=False)
    allowed = db_path_guard.DEMO_DB_PATH.resolve(strict=False)
    if resolved != allowed:
        raise RefusedRealDatabaseError(
            f"dashboard_demo_seed.py only ever writes to the demo database ({allowed}); "
            f"refusing to touch {resolved}"
        )
    return resolved


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
    resolved = _require_demo_path(path)

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
            if status != "FAILED":
                _insert_snapshot(conn, "r-demo-old-complete", symbol, "2026-09-01", "2026-09-01T09:20:00+05:30", 100.0)
        _complete_run(
            conn, "r-demo-old-complete", "2026-09-01T09:45:00", "2026-09-01",
            status_counts, flag_counts,
            requested=len(FAKE_SYMBOLS),
            successful=status_counts["VALID"],
            failed=status_counts["FAILED"],
        )
        conn.commit()

        # r1b: the previous COMPLETE full run, started after r1 and before
        # r2, sharing three bar dates with r2 so the snapshot-audit view has
        # something to compare. Its bars are the baseline: r2 revises a few.
        _insert_scan_run(conn, "r-demo-prev-complete", "2026-09-26T09:20:00")
        for i, (symbol, name, sector, status, reason, flags) in enumerate(FAKE_SYMBOLS):
            _insert_symbol_result(conn, "r-demo-prev-complete", symbol, name, sector, status, reason, flags)
            for d in _bar_dates_for(status):
                _insert_snapshot(conn, "r-demo-prev-complete", symbol, d, "2026-09-26T09:20:00+05:30",
                                 *_bar_values(i, d, revised=False))
        _complete_run(
            conn, "r-demo-prev-complete", "2026-09-26T09:45:00", SESSION_DATE,
            status_counts, flag_counts,
            requested=len(FAKE_SYMBOLS),
            successful=status_counts["VALID"],
            failed=status_counts["FAILED"],
        )
        conn.commit()

        # r2: the latest COMPLETE run -- the one the Overview page should
        # show. Its latest_closed_session is SESSION_DATE (fixed, a Friday),
        # so seeding is deterministic; see the comment on BAR_DATES for what
        # that means for the OUTDATED banner. Some bars are revised relative
        # to r1b (see _bar_values), so the audit view has changes to show.
        latest_session = SESSION_DATE
        _insert_scan_run(conn, "r-demo-latest-complete", "2026-09-27T09:20:00")
        for i, (symbol, name, sector, status, reason, flags) in enumerate(FAKE_SYMBOLS):
            _insert_symbol_result(conn, "r-demo-latest-complete", symbol, name, sector, status, reason, flags)
            for d in _bar_dates_for(status):
                _insert_snapshot(conn, "r-demo-latest-complete", symbol, d, "2026-09-27T09:20:00+05:30",
                                 *_bar_values(i, d, revised=True))
        _complete_run(
            conn, "r-demo-latest-complete", "2026-09-27T09:45:00", latest_session,
            status_counts, flag_counts,
            requested=len(FAKE_SYMBOLS),
            successful=status_counts["VALID"],
            failed=status_counts["FAILED"],
        )
        conn.commit()

        # r2b: a newer --symbols smoke run (COMPLETE but not a full run): the
        # dashboard must keep showing r2 and name this run as newer.
        smoke = FAKE_SYMBOLS[:2]
        _insert_scan_run(conn, "r-demo-smoke", "2026-09-28T09:20:00",
                         symbols_filter_json=json.dumps([x[0] for x in smoke]))
        for symbol, name, sector, status, reason, flags in smoke:
            _insert_symbol_result(conn, "r-demo-smoke", symbol, name, sector, status, reason, flags)
        s_counts, s_flags = _status_and_flag_counts(smoke)
        _complete_run(conn, "r-demo-smoke", "2026-09-28T09:25:00", latest_session, s_counts, s_flags,
                      requested=len(smoke), successful=s_counts["VALID"], failed=s_counts["FAILED"])
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

    _seed_e4_tables(resolved, latest_session)


def _weekdays_ending(end_iso: str, n: int) -> list[str]:
    day, out = date.fromisoformat(end_iso), []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return list(reversed(out))


def _seed_e4_tables(resolved: Path, latest_session: str) -> None:
    """Fabricated E4 acquisition + feature tables for the demo database.

    Applies the exact-DEMO_DB_PATH guard itself, before opening anything:
    connection.connect() would also accept the canonical equity_intel.db, so
    its own allow-list is not a sufficient protection here.
    """
    resolved = _require_demo_path(resolved)
    dates = _weekdays_ending(latest_session, E4_DEMO_BARS + 1)  # one spare for STALE symbols
    acq, e4 = "demo-acq-1", "demo-e4-1"
    conn = connection.connect(resolved)
    try:
        conn.execute(
            "INSERT INTO acquisition_runs(run_id,run_started_at,run_completed_at,status,report_json) VALUES(?,?,?,?,?)",
            (acq, "2026-09-27T09:00:00", "2026-09-27T09:10:00", "COMPLETE",
             json.dumps({"adjustment_status": DEMO_ADJUSTMENT_STATUS, "benchmark_key": "DEMO_INDEX",
                         "benchmark_observation_count": len(dates), "benchmark_status": "OK"})),
        )
        for d in dates:
            conn.execute(
                "INSERT INTO acquired_benchmark VALUES(?,?,?,?,?,?)",
                (acq, "DEMO_INDEX", d, 1000.0, "demo-seed", "2026-09-27T09:00:00+05:30"),
            )
        conn.execute(
            "INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,completed_at,status,asof_date,"
            "calendar_status,indicator_config_json) VALUES(?,?,?,?,?,?,?,?)",
            (e4, acq, "2026-09-27T09:12:00", "2026-09-27T09:13:00", "COMPLETE", latest_session, "PROVISIONAL",
             json.dumps(DEMO_E4_CONFIG)),
        )
        for i, (symbol, _name, _sector, status, reason, flags) in enumerate(FAKE_SYMBOLS):
            if status == "FAILED":
                continue  # no bars, no E4 rows: the dashboard must show "not recorded"
            n_bars = 41 if status == "INSUFFICIENT_HISTORY" else E4_DEMO_BARS
            # a STALE symbol's newest observation is one session older than the E4 as-of date
            symbol_dates = dates[-(n_bars + 1):-1] if status == "STALE" else dates[-n_bars:]
            for j, d in enumerate(symbol_dates):
                close = 100.0 + i + j * 0.1
                conn.execute(
                    "INSERT INTO acquired_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (acq, symbol, d, close - 1, close + 2, close - 2, close, 1_000_000.0 + j,
                     "demo-seed", "demo", "2026-09-27T09:00:00+05:30", f"DEMO|{symbol}", "NSE",
                     "PROVISIONAL", DEMO_ADJUSTMENT_STATUS, acq),
                )
            full = status == "VALID"
            complete = n_bars >= DEMO_E4_CONFIG["minimum_history_bars"]  # w52_complete / volume_usable follow bar count
            reason_e4 = None if full else reason
            break_date = symbol_dates[len(symbol_dates) // 2] if flags["price_break_detected"] else None
            conn.execute(
                "INSERT INTO e4_data_quality_results VALUES(?,?,?,?,?,?,?,?,?)",
                (e4, symbol, status, reason_e4, n_bars, int(complete), break_date,
                 0.45 if break_date else None, int(complete)),
            )
            if full:
                last = 100.0 + i + (E4_DEMO_BARS - 1) * 0.1
                conn.execute(
                    "INSERT INTO e4_feature_sets(scan_id,symbol,last_date,ema_short,ema_medium,ema_long,rsi,roc,"
                    "relative_return,relative_volume,distance_from_high,prior_high_long,atr_percent) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (e4, symbol, symbol_dates[-1], last - 0.5, last - 1.5, last - 3.0, 50.0 + i % 20, 1.0 + i % 5,
                     0.5 + i % 7, 0.8 + (i % 10) / 10, 2.0 + i % 8, last + 2.0 + i % 8, 1.5),
                )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_demo_database()
    print(f"Seeded demo database at {db_path_guard.DEMO_DB_PATH.resolve(strict=False)}")

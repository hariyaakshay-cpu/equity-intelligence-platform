"""ScanRun row lifecycle (Section 9).

Status lifecycle: RUNNING -> COMPLETE | ABORTED. No PARTIAL, no FAILED at
the run level (FAILED is reserved for symbol_data_status). Every write
here goes through equity_intel.scanner.db.get_scan_connection's caller --
this module takes an already-open connection, it never opens one itself.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from equity_intel.config import IST
from equity_intel.persistence.db_path_guard import REPO_ROOT

# Recorded as scan_runs.abort_reason for a ScanRun that was still RUNNING
# when a new scanner process started -- Section 9: "On scanner start, any
# ScanRun still RUNNING from before is marked ABORTED
# (abort_reason=INTERRUPTED)." This is the only abort reason set here
# rather than raised by another module as an exception, since there is no
# in-progress run to catch an exception from -- it describes a *previous*
# process's run, discovered at the start of this one.
INTERRUPTED = "INTERRUPTED"

# abort_reason for an exception that escaped the pipeline outside the
# per-symbol isolation (scripts/equity_scan.py's top-level handler).
# KeyboardInterrupt/SystemExit reuse INTERRUPTED above.
UNEXPECTED_ERROR = "UNEXPECTED_ERROR"

RUNNING = "RUNNING"
COMPLETE = "COMPLETE"
ABORTED = "ABORTED"


def _now_ist(now: Optional[datetime]) -> datetime:
    return now if now is not None else datetime.now(IST)


def _now_ist_iso(now: Optional[datetime]) -> str:
    return _now_ist(now).isoformat()


def _git_commit_and_dirty(repo_root: Path = REPO_ROOT) -> "tuple[Optional[str], Optional[bool]]":
    """Best-effort: (HEAD commit hash, whether the working tree is dirty).
    (None, None) if git isn't available or this isn't a git checkout --
    recording git provenance is a diagnostic nicety, never a reason to
    fail a scan run."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, stderr=subprocess.DEVNULL, timeout=5
        ).decode()
        return commit, bool(status.strip())
    except Exception:
        return None, None


def mark_stale_running_as_interrupted(conn, *, now: Optional[datetime] = None) -> int:
    """Mark every scan_runs row still RUNNING (necessarily left over from
    a previous, now-dead process, since a single scan runs synchronously
    start to finish) as ABORTED/INTERRUPTED. Called once, at the very
    start of a new scan, before that new run's own row is inserted -- so
    every RUNNING row this finds is guaranteed to belong to a prior run,
    never the one about to start.

    Returns the number of rows marked.
    """
    stale_run_ids = [
        row[0] for row in conn.execute("SELECT run_id FROM scan_runs WHERE status = ?", (RUNNING,)).fetchall()
    ]
    finished_at = _now_ist_iso(now)
    for run_id in stale_run_ids:
        conn.execute(
            "UPDATE scan_runs SET status = ?, abort_reason = ?, finished_at = ? WHERE run_id = ?",
            (ABORTED, INTERRUPTED, finished_at, run_id),
        )
    conn.commit()
    return len(stale_run_ids)


def start_scan_run(
    conn,
    *,
    run_id: str,
    requested_symbols: int,
    price_source: str = "upstox",
    symbols_filter: Optional[Sequence[str]] = None,
    now: Optional[datetime] = None,
) -> None:
    """Mark any leftover RUNNING rows INTERRUPTED, then insert this run's
    own row as RUNNING. schema.py's prevent_scan_run_insert_not_running
    trigger requires every inserted row to start RUNNING -- COMPLETE/
    ABORTED are only ever reached by a later UPDATE.

    `symbols_filter`: the --symbols list for a smoke run, or None for a
    full-universe run. Persisted as symbols_filter_json (NULL when None)
    so the dashboard can tell a smoke run apart from a real scan (Section
    10) -- get_latest_complete_run only ever considers a NULL row "the
    latest COMPLETE run".
    """
    mark_stale_running_as_interrupted(conn, now=now)
    git_commit, git_dirty = _git_commit_and_dirty()
    conn.execute(
        """
        INSERT INTO scan_runs
            (run_id, started_at, status, requested_symbols, price_source,
             symbols_filter_json, git_commit, git_dirty, scoring_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'BLOCKED_B2')
        """,
        (
            run_id,
            _now_ist_iso(now),
            RUNNING,
            requested_symbols,
            price_source,
            json.dumps(sorted(symbols_filter)) if symbols_filter else None,
            git_commit,
            None if git_dirty is None else int(git_dirty),
        ),
    )
    conn.commit()


def abort_scan_run(
    conn,
    *,
    run_id: str,
    abort_reason: str,
    errors: Optional[Sequence[str]] = None,
    now: Optional[datetime] = None,
) -> None:
    """End a RUNNING row as ABORTED. Valid at any point in the pipeline --
    an abort can happen before universe/review-list loading even finishes
    (Section 9), so no other field is required here."""
    conn.execute(
        "UPDATE scan_runs SET status = ?, abort_reason = ?, finished_at = ?, errors_json = ? WHERE run_id = ?",
        (ABORTED, abort_reason, _now_ist_iso(now), json.dumps(list(errors)) if errors else None, run_id),
    )
    conn.commit()


def abort_scan_run_if_running(
    conn,
    *,
    run_id: str,
    abort_reason: str,
    errors: Optional[Sequence[str]] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Like abort_scan_run, but a no-op unless the row is still RUNNING
    (a finished row is frozen by trigger and must not be touched). For the
    last-resort top-level handler, which cannot know how far the run got.
    Returns True if a row was aborted."""
    cursor = conn.execute(
        "UPDATE scan_runs SET status = ?, abort_reason = ?, finished_at = ?, errors_json = ? "
        "WHERE run_id = ? AND status = ?",
        (ABORTED, abort_reason, _now_ist_iso(now), json.dumps(list(errors)) if errors else None, run_id, RUNNING),
    )
    conn.commit()
    return cursor.rowcount > 0


def complete_scan_run(
    conn,
    *,
    run_id: str,
    universe_version: str,
    corporate_action_review_version: str,
    benchmark: str,
    calendar_source: str,
    calendar_verification: str,
    latest_closed_session: str,
    calendar_dates: Sequence[str],
    successful_symbols: int,
    failed_symbols: int,
    status_counts: dict,
    flag_counts: dict,
    excluded_symbols: Sequence[dict],
    errors: Optional[Sequence[str]] = None,
    now: Optional[datetime] = None,
) -> None:
    """End a RUNNING row as COMPLETE, in one final UPDATE. schema.py's
    CHECK constraint refuses this unless both universe_version and
    corporate_action_review_version are non-NULL, matching Section 9:
    COMPLETE means every requested symbol has a persisted outcome, not
    that all data is good.
    """
    conn.execute(
        """
        UPDATE scan_runs SET
            status = ?,
            finished_at = ?,
            universe_version = ?,
            corporate_action_review_version = ?,
            benchmark = ?,
            calendar_source = ?,
            calendar_verification = ?,
            latest_closed_session = ?,
            calendar_dates_json = ?,
            successful_symbols = ?,
            failed_symbols = ?,
            status_counts_json = ?,
            flag_counts_json = ?,
            excluded_symbols_json = ?,
            errors_json = ?
        WHERE run_id = ?
        """,
        (
            COMPLETE,
            _now_ist_iso(now),
            universe_version,
            corporate_action_review_version,
            benchmark,
            calendar_source,
            calendar_verification,
            latest_closed_session,
            json.dumps(list(calendar_dates)),
            successful_symbols,
            failed_symbols,
            json.dumps(status_counts),
            json.dumps(flag_counts),
            json.dumps(list(excluded_symbols)),
            json.dumps(list(errors)) if errors else None,
            run_id,
        ),
    )
    conn.commit()

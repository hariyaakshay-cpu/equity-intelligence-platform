"""Single-instance lock for the scanner process.

Prevents two scan processes from running concurrently against the same
database. This is not something SQLite's own locking solves for us here:
the risk isn't a corrupted write, it's ScanRun lifecycle logic drawing
the wrong conclusion. equity_intel.scanner.scan_run.
mark_stale_running_as_interrupted assumes every scan_runs row still
RUNNING belongs to a *dead* process and is therefore safe to mark
ABORTED/INTERRUPTED. That assumption is false while a second process is
genuinely still running. This lock is acquired *before* start_scan_run()
(and therefore before mark_stale_running_as_interrupted) ever runs, so a
live second process is refused outright -- it never reaches, and
therefore never corrupts, another live run's row.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from equity_intel.config import IST


class ScannerAlreadyRunningError(RuntimeError):
    """Raised when the scan lock file already exists. Never silently
    proceeds, and never treats this as a stale/dead process on its own --
    see module docstring. The caller decides, by reading the message (or
    the file itself), whether to remove a truly stale lock and retry."""


def acquire_scan_lock(path: Path, *, now: Optional[datetime] = None) -> None:
    """Create the lock file at `path`, refusing if one already exists.

    Raises:
        ScannerAlreadyRunningError: `path` already exists. The message
            includes its contents (PID, start time) and instructions for
            removing it if it is stale (a previous process crashed
            without cleaning up) -- this function never removes or
            overwrites an existing lock file itself.
    """
    if path.exists():
        contents = path.read_text(encoding="utf-8")
        raise ScannerAlreadyRunningError(
            "Refusing to start: another scan appears to be running "
            f"(lock file present at {path}):\n{contents}\n"
            "If you're certain no scan is actually running (e.g. a previous "
            f"process crashed without cleaning up), delete this file and try again: {path}"
        )
    payload = {"pid": os.getpid(), "started_at": (now if now is not None else datetime.now(IST)).isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def release_scan_lock(path: Path) -> None:
    """Remove the lock file at `path`. A no-op if it's already gone (e.g.
    removed manually, or acquire_scan_lock never got as far as creating
    it in the first place)."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass

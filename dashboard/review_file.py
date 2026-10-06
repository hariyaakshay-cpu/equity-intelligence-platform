"""Read-only reader for the corporate-action review CSV, shared by the dashboard pages.

Reads the file and reports its state; never writes. A header-only file is the normal
"nothing under review" state and is reported as "empty", never as "0 issues".

Like queries.py this module never imports sqlite3.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from equity_intel.scanner import corporate_actions


def read_review_file(path: Path, run_version: Optional[str]) -> dict:
    """The current state of the review CSV at `path`.

    Keys: file_state ("unavailable" | "empty" | "has_entries"), message (None unless
    unavailable or empty), entries (every ReviewEntry in the file, unfiltered), and
    version_note when `run_version` (the version the run recorded) differs from the
    file on disk.
    """
    state: dict = {"file_state": None, "message": None, "entries": []}
    try:
        loaded = corporate_actions.load_corporate_action_review(path)
    except corporate_actions.CorporateActionReviewCSVInvalidError as exc:
        state["file_state"] = "unavailable"
        state["message"] = f"review file unavailable: {exc}"
        return state
    if not loaded.entries:
        state["file_state"] = "empty"
        state["message"] = "review file empty: no symbols reviewed"
    else:
        state["file_state"] = "has_entries"
        state["entries"] = list(loaded.entries)
    if run_version and run_version != loaded.version:
        state["version_note"] = ("the review file on disk differs from the version this run used "
                                 "(it was edited after the run); entries below are the CURRENT file")
    return state

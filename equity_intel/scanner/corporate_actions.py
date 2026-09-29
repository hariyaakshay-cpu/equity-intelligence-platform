"""Manual corporate-action review list (Section 7).

Loads data/reference/corporate_action_review.csv once per scan run and
applies it to that run's symbol results -- the CSV itself is never
persisted into data/equity_intel.db as its own table; only its *effect*
(the CORPORATE_ACTION_REVIEW flag) and its content hash
(corporate_action_review_version) are.

No automation here at all: no price-jump detection (that is
PRICE_BREAK_DETECTED, classification.py, a separate mechanism) and no
automatic demerger/split adjustment. This module only reads the list and
answers "is this symbol under review, for this run's fetched window".

Missing-file and empty-file are different cases and must not be
conflated (Section 7): a header-only file is the normal "nothing under
review" state; a missing or unreadable file means the scanner cannot
know that, so the run must abort rather than silently treat it as empty.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

from equity_intel.scanner.universe import sha256_file

# Recorded as scan_runs.abort_reason when the review CSV is missing or
# cannot be read/parsed (Section 7). Wiring the actual RUNNING -> ABORTED
# transition is scan_run.py's job; this module only raises
# CorporateActionReviewCSVInvalidError and exposes the reason string for
# that caller.
CORPORATE_ACTION_REVIEW_CSV_INVALID = "CORPORATE_ACTION_REVIEW_CSV_INVALID"

_RESOLVED_STATE = "RESOLVED"


class CorporateActionReviewCSVInvalidError(RuntimeError):
    """Raised when the review CSV is missing, unreadable, or malformed
    (missing a required column). Never raised for a valid header-only
    (zero data rows) file -- that is the normal empty state."""


@dataclass(frozen=True)
class ReviewEntry:
    symbol: str
    isin: str
    event_type: str
    effective_date: str  # ISO date string
    reason: str
    reviewer: str
    review_state: str


@dataclass(frozen=True)
class CorporateActionReview:
    entries: List[ReviewEntry]
    version: str  # SHA-256 hex digest of the CSV file, unmodified


_REQUIRED_COLUMNS = ("symbol", "isin", "event_type", "effective_date", "reason", "reviewer", "review_state")


def load_corporate_action_review(csv_path: Union[str, Path]) -> CorporateActionReview:
    """Load and hash the review CSV.

    Raises:
        CorporateActionReviewCSVInvalidError: the file does not exist,
            can't be read, or is missing a required column. A header-only
            file (zero data rows) is valid and returns an empty entries
            list, not an error.
    """
    path = Path(csv_path)
    try:
        version = sha256_file(path)
    except OSError as exc:
        raise CorporateActionReviewCSVInvalidError(f"cannot read corporate action review CSV {path}: {exc}") from exc

    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or ()
            missing = [col for col in _REQUIRED_COLUMNS if col not in fieldnames]
            if missing:
                raise CorporateActionReviewCSVInvalidError(
                    f"corporate action review CSV {path} is missing required column(s): {missing}"
                )
            entries = [
                ReviewEntry(
                    symbol=row["symbol"].strip(),
                    isin=(row["isin"] or "").strip(),
                    event_type=row["event_type"].strip(),
                    effective_date=row["effective_date"].strip(),
                    reason=row["reason"].strip(),
                    reviewer=row["reviewer"].strip(),
                    review_state=row["review_state"].strip(),
                )
                for row in reader
            ]
    except OSError as exc:
        raise CorporateActionReviewCSVInvalidError(f"cannot read corporate action review CSV {path}: {exc}") from exc
    except csv.Error as exc:
        raise CorporateActionReviewCSVInvalidError(f"corporate action review CSV {path} is malformed: {exc}") from exc

    return CorporateActionReview(entries=entries, version=version)


def is_under_review(
    review: CorporateActionReview,
    symbol: str,
    window_start: str,
    window_end: str,
) -> bool:
    """True if `symbol` has a non-RESOLVED review entry whose
    effective_date falls inside [window_start, window_end] (the symbol's
    fetched window, both ISO date strings, inclusive) -- Section 7.
    """
    return any(
        entry.symbol == symbol
        and entry.review_state != _RESOLVED_STATE
        and window_start <= entry.effective_date <= window_end
        for entry in review.entries
    )

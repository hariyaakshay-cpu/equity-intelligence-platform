"""ScanRun contract -- the run-level audit record for one scanner execution.

Field names and the status lifecycle (RUNNING -> COMPLETE | ABORTED, no
PARTIAL) are fixed by docs/architecture/equity_intel_scanner_v1_spec.md,
Section 9, not invented here. scoring_status defaults to BLOCKED_B2: B2
scoring is not implemented anywhere in this package, so no code path can
produce a real score for this field to report instead.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence


class ScanRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"


SCORING_STATUS_BLOCKED_B2 = "BLOCKED_B2"
CALENDAR_VERIFICATION_UNVERIFIED_INDEX_ONLY = "UNVERIFIED_INDEX_ONLY"


@dataclass
class ScanRun:
    run_id: str
    started_at: str
    status: ScanRunStatus
    finished_at: Optional[str] = None
    abort_reason: Optional[str] = None
    universe_version: Optional[str] = None
    corporate_action_review_version: Optional[str] = None
    benchmark: Optional[str] = None
    calendar_source: Optional[str] = None
    calendar_verification: Optional[str] = None
    latest_closed_session: Optional[str] = None
    calendar_dates: Sequence[str] = field(default_factory=tuple)
    price_source: Optional[str] = None
    requested_symbols: Optional[int] = None
    successful_symbols: Optional[int] = None
    failed_symbols: Optional[int] = None
    status_counts: Dict[str, int] = field(default_factory=dict)
    flag_counts: Dict[str, int] = field(default_factory=dict)
    excluded_symbols: Sequence[Dict[str, str]] = field(default_factory=tuple)
    errors: Sequence[str] = field(default_factory=tuple)
    git_commit: Optional[str] = None
    git_dirty: Optional[bool] = None
    scoring_status: str = SCORING_STATUS_BLOCKED_B2

"""ScanRun contract shape tests -- no business logic, no I/O."""
from equity_intel.contracts.scan_run import (
    CALENDAR_VERIFICATION_UNVERIFIED_INDEX_ONLY,
    SCORING_STATUS_BLOCKED_B2,
    ScanRun,
    ScanRunStatus,
)


def test_scan_run_status_vocabulary_is_exactly_running_complete_aborted():
    assert {s.value for s in ScanRunStatus} == {"RUNNING", "COMPLETE", "ABORTED"}


def test_scan_run_defaults_scoring_status_to_blocked_b2():
    run = ScanRun(run_id="R1", started_at="2026-09-27T00:00:00", status=ScanRunStatus.RUNNING)
    assert run.scoring_status == "BLOCKED_B2"
    assert run.scoring_status == SCORING_STATUS_BLOCKED_B2


def test_scan_run_optional_fields_default_to_none_or_empty():
    run = ScanRun(run_id="R1", started_at="2026-09-27T00:00:00", status=ScanRunStatus.RUNNING)
    assert run.abort_reason is None
    assert run.universe_version is None
    assert run.corporate_action_review_version is None
    assert run.calendar_dates == ()
    assert run.status_counts == {}
    assert run.flag_counts == {}
    assert run.excluded_symbols == ()
    assert run.errors == ()


def test_calendar_verification_constant_matches_the_frozen_spec_value():
    assert CALENDAR_VERIFICATION_UNVERIFIED_INDEX_ONLY == "UNVERIFIED_INDEX_ONLY"


def test_scan_run_has_no_broker_or_oms_fields():
    run = ScanRun(run_id="R1", started_at="2026-09-27T00:00:00", status=ScanRunStatus.RUNNING)
    forbidden_substrings = ("broker", "order", "oms", "position", "execution")
    for name in run.__dataclass_fields__:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), name

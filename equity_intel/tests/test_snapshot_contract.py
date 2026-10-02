"""PriceFetchSnapshot contract shape tests -- no business logic, no I/O."""
from decimal import Decimal

from equity_intel.contracts.snapshot import CandleValidationStatus, PriceFetchSnapshot


def _make_snapshot(**overrides):
    defaults = dict(
        scan_run_id="R1",
        symbol="TCS",
        trading_date="2026-09-25",
        source="upstox",
        fetched_at_ist="2026-09-27T18:05:00+05:30",
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("99.00"),
        close=Decimal("104.00"),
        volume=1000,
        content_hash="deadbeef",
        candle_validation_status=CandleValidationStatus.VALID,
    )
    defaults.update(overrides)
    return PriceFetchSnapshot(**defaults)


def test_candle_validation_status_vocabulary_is_exactly_valid_invalid():
    assert {s.value for s in CandleValidationStatus} == {"VALID", "INVALID"}


def test_snapshot_defaults_validation_errors_and_source_metadata_to_empty():
    snapshot = _make_snapshot()
    assert snapshot.validation_errors == ()
    assert snapshot.source_metadata == {}


def test_snapshot_is_frozen_immutable():
    snapshot = _make_snapshot()
    try:
        snapshot.close = Decimal("999.00")
        assert False, "expected a FrozenInstanceError"
    except AttributeError:
        pass


def test_snapshot_has_no_broker_or_oms_fields():
    snapshot = _make_snapshot()
    forbidden_substrings = ("broker", "order", "oms", "position", "execution")
    for name in snapshot.__dataclass_fields__:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), name


def test_snapshot_allows_null_fields_as_none_not_zero():
    snapshot = _make_snapshot(open=None, volume=None)
    assert snapshot.open is None
    assert snapshot.volume is None

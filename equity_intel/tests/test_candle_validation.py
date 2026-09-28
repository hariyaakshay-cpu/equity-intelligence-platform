"""Tests for equity_intel.scanner.candle_validation."""
from equity_intel.scanner.candle_validation import (
    CLOSE_OUTSIDE_RANGE,
    HIGH_LESS_THAN_LOW,
    INVALID,
    MISSING_FIELD,
    NEGATIVE_VOLUME,
    NON_POSITIVE_CLOSE,
    NON_POSITIVE_HIGH,
    NON_POSITIVE_LOW,
    NON_POSITIVE_OPEN,
    OPEN_OUTSIDE_RANGE,
    VALID,
    validate_candle,
)


def test_a_clean_candle_is_valid():
    status, errors = validate_candle(open_=100, high=105, low=99, close=102, volume=1000)
    assert status == VALID
    assert errors == []


def test_missing_open_is_invalid_with_missing_field_only():
    status, errors = validate_candle(open_=None, high=105, low=99, close=102, volume=1000)
    assert status == INVALID
    assert errors == [MISSING_FIELD]


def test_missing_volume_is_invalid_with_missing_field_only():
    status, errors = validate_candle(open_=100, high=105, low=99, close=102, volume=None)
    assert status == INVALID
    assert errors == [MISSING_FIELD]


def test_high_less_than_low_is_flagged():
    status, errors = validate_candle(open_=100, high=90, low=95, close=92, volume=1000)
    assert status == INVALID
    assert HIGH_LESS_THAN_LOW in errors


def test_open_outside_high_low_range_is_flagged():
    status, errors = validate_candle(open_=200, high=105, low=99, close=102, volume=1000)
    assert status == INVALID
    assert OPEN_OUTSIDE_RANGE in errors


def test_close_outside_high_low_range_is_flagged():
    status, errors = validate_candle(open_=100, high=105, low=99, close=1, volume=1000)
    assert status == INVALID
    assert CLOSE_OUTSIDE_RANGE in errors


def test_non_positive_prices_are_each_flagged():
    status, errors = validate_candle(open_=0, high=0, low=-1, close=0, volume=1000)
    assert status == INVALID
    assert NON_POSITIVE_OPEN in errors
    assert NON_POSITIVE_HIGH in errors
    assert NON_POSITIVE_LOW in errors
    assert NON_POSITIVE_CLOSE in errors


def test_negative_volume_is_flagged():
    status, errors = validate_candle(open_=100, high=105, low=99, close=102, volume=-5)
    assert status == INVALID
    assert NEGATIVE_VOLUME in errors


def test_zero_volume_is_not_flagged():
    status, errors = validate_candle(open_=100, high=105, low=99, close=102, volume=0)
    assert status == VALID
    assert errors == []


def test_open_equal_to_high_or_low_boundary_is_valid():
    status, errors = validate_candle(open_=105, high=105, low=99, close=99, volume=1000)
    assert status == VALID
    assert errors == []


def test_a_candle_valid_raw_but_non_positive_after_2dp_rounding_is_flagged():
    # open=0.001 and low=0.002 are both positive raw floats within a
    # perfectly sane [low, high] range -- valid by every check if you
    # compare raw values. But both round (ROUND_HALF_UP, 2dp) down to
    # "0.00", the same value that gets stored and hashed by
    # snapshots.write_snapshot -- so validation (which now runs on that
    # same quantized value, not the raw float) must flag them as
    # non-positive even though they were never negative or zero raw.
    status, errors = validate_candle(open_=0.002, high=105, low=0.001, close=50, volume=1000)
    assert status == INVALID
    assert NON_POSITIVE_OPEN in errors
    assert NON_POSITIVE_LOW in errors

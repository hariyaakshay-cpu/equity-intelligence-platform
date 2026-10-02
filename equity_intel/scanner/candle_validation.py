"""Structural candle validation.

Per docs/architecture/equity_intel_scanner_v1_spec.md Section 5: structural
checks only -- missing fields/nulls, high < low, open or close outside
[low, high], non-positive prices, negative volume. No statistical or jump
threshold (that is PRICE_BREAK_DETECTED, a separate per-symbol flag
computed across a series -- Section 6, Phase 3, not this per-candle check).

All comparisons run on the same 2dp-quantized (ROUND_HALF_UP) values that
snapshots.write_snapshot actually stores, via
equity_intel.scanner.snapshots.quantize_price -- not on the raw vendor
floats. A candle is validated as what will be persisted, not as what was
received: a price that rounds down across zero (e.g. 0.001 -> "0.00") must
be flagged even though the raw float is positive. Quantization is
monotonic, so it can only ever turn a structurally-valid candle invalid
this way (by crossing a fixed boundary like zero) -- it can never turn a
genuinely invalid one (e.g. high < low) valid, since rounding never
reverses the relative order of two values.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from equity_intel.scanner.snapshots import quantize_price

VALID = "VALID"
INVALID = "INVALID"

MISSING_FIELD = "MISSING_FIELD"
HIGH_LESS_THAN_LOW = "HIGH_LESS_THAN_LOW"
OPEN_OUTSIDE_RANGE = "OPEN_OUTSIDE_RANGE"
CLOSE_OUTSIDE_RANGE = "CLOSE_OUTSIDE_RANGE"
NON_POSITIVE_OPEN = "NON_POSITIVE_OPEN"
NON_POSITIVE_HIGH = "NON_POSITIVE_HIGH"
NON_POSITIVE_LOW = "NON_POSITIVE_LOW"
NON_POSITIVE_CLOSE = "NON_POSITIVE_CLOSE"
NEGATIVE_VOLUME = "NEGATIVE_VOLUME"

_NON_POSITIVE_BY_FIELD = {
    "open": NON_POSITIVE_OPEN,
    "high": NON_POSITIVE_HIGH,
    "low": NON_POSITIVE_LOW,
    "close": NON_POSITIVE_CLOSE,
}


def validate_candle(
    open_: Optional[float],
    high: Optional[float],
    low: Optional[float],
    close: Optional[float],
    volume: Optional[int],
) -> Tuple[str, List[str]]:
    """Returns (candle_validation_status, validation_errors).

    If any of open/high/low/close/volume is missing, every other
    structural check is skipped (there is nothing well-defined to compare)
    and only MISSING_FIELD is reported -- never a spurious
    HIGH_LESS_THAN_LOW etc. derived from comparing against a missing value.
    """
    fields = {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    if any(value is None for value in fields.values()):
        return INVALID, [MISSING_FIELD]

    q = {name: quantize_price(fields[name]) for name in ("open", "high", "low", "close")}

    errors: List[str] = []

    if q["high"] < q["low"]:
        errors.append(HIGH_LESS_THAN_LOW)
    if not (q["low"] <= q["open"] <= q["high"]):
        errors.append(OPEN_OUTSIDE_RANGE)
    if not (q["low"] <= q["close"] <= q["high"]):
        errors.append(CLOSE_OUTSIDE_RANGE)
    for field_name in ("open", "high", "low", "close"):
        if q[field_name] <= 0:
            errors.append(_NON_POSITIVE_BY_FIELD[field_name])
    if volume < 0:
        errors.append(NEGATIVE_VOLUME)

    status = INVALID if errors else VALID
    return status, errors

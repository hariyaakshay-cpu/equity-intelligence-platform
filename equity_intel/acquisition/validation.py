from __future__ import annotations

from datetime import date
from math import isfinite

from equity_intel.acquisition.models import Candle, ValidationResult


def validate_candles(candles: list[Candle], as_of: date | None = None) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not candles:
        return ValidationResult("INVALID", ("No observations returned",))
    dates = [c.trading_date for c in candles]
    if any(d is None for d in dates):
        errors.append("Missing or invalid trading date")
    valid_dates = [d for d in dates if d is not None]
    if len(set(valid_dates)) != len(valid_dates):
        errors.append("Duplicate trading dates")
    if valid_dates != sorted(valid_dates):
        errors.append("Trading dates are not in ascending order")
    if as_of and any(d > as_of for d in valid_dates):
        errors.append("Future observation date")
    required = ("open", "high", "low", "close", "volume")
    for idx, candle in enumerate(candles):
        values = {name: getattr(candle, name) for name in required}
        missing = [name for name, value in values.items() if value is None]
        if missing:
            errors.append(f"Observation {idx}: missing {', '.join(missing)}")
            continue
        if any(not isfinite(float(value)) for value in values.values()):
            errors.append(f"Observation {idx}: non-finite OHLCV value")
            continue
        o, h, l, c, v = (float(values[k]) for k in required)
        if min(o, h, l, c) <= 0:
            errors.append(f"Observation {idx}: non-positive price")
        if h < max(o, c, l):
            errors.append(f"Observation {idx}: high below open/close/low")
        if l > min(o, c, h):
            errors.append(f"Observation {idx}: low above open/close/high")
        if v < 0:
            errors.append(f"Observation {idx}: negative volume")
        elif v == 0:
            warnings.append(f"Observation {idx}: zero volume")
    status = "INVALID" if errors else "VALID_WITH_WARNINGS" if warnings else "VALID"
    return ValidationResult(status, tuple(errors), tuple(warnings))

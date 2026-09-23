"""Rolling-high / distance-from-high -- pure math, no fixed window or band."""
from __future__ import annotations

from typing import Optional, Sequence


def rolling_high(values: Sequence[float], window: int, *, exclude_current: bool) -> Optional[float]:
    """Maximum of the trailing `window` observations.

    `exclude_current` controls whether the most recent observation is
    included (needed both by "prior N-day high, excluding today" and by
    "N-bar high including today" -- B2 spec Section 4.5 uses both
    conventions for different windows; this function does not choose
    between them, the caller does).
    """
    if window <= 0:
        raise ValueError("window must be a positive integer")
    if exclude_current:
        series = values[:-1]
        if len(series) < window:
            return None
        return max(series[-window:])
    if len(values) < window:
        return None
    return max(values[-window:])


def distance_from_high(current: float, high: float) -> Optional[float]:
    """Percent distance of `current` below `high`. None if `high` is not
    positive (cannot express a meaningful percentage)."""
    if high is None or high <= 0:
        return None
    return (high - current) / high * 100.0

"""Exponential moving average -- pure math, no fixed period."""
from __future__ import annotations

from typing import List, Optional, Sequence


def exponential_moving_average(
    closes: Sequence[float], period: int
) -> Optional[List[Optional[float]]]:
    """Return an EMA series aligned to `closes`, seeded by a simple mean of
    the first `period` values, or None if there are fewer than `period`
    observations.

    `period` is a required argument. This function does not assume 20, 50,
    or 200 (the periods proposed, not approved, in B2 spec Section 4.1) --
    callers choose the period explicitly.
    """
    if period <= 0:
        raise ValueError("period must be a positive integer")
    n = len(closes)
    if n < period:
        return None
    seed = sum(closes[:period]) / period
    alpha = 2.0 / (period + 1)
    series: List[Optional[float]] = [None] * (period - 1) + [seed]
    e = seed
    for c in closes[period:]:
        e = alpha * c + (1 - alpha) * e
        series.append(e)
    return series

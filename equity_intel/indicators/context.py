"""ATR -- context-only indicator, pure math.

Per B2 invariant I5, ATR/volatility may be computed and displayed but must
never feed any component score or the composite. This module produces the
raw ATR percentage only; nothing in this package wires its output into a
ComponentResult or CompositeResult.
"""
from __future__ import annotations

from typing import Optional, Sequence


def average_true_range(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int
) -> Optional[float]:
    if period <= 0:
        raise ValueError("period must be a positive integer")
    n = len(closes)
    if n < period + 1:
        return None
    true_ranges = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def atr_percent(atr_value: Optional[float], close: float) -> Optional[float]:
    if atr_value is None or close is None or close == 0:
        return None
    return atr_value / close * 100.0

"""RSI (Wilder) and rate-of-change -- pure math, no fixed period/bands."""
from __future__ import annotations

from typing import Optional, Sequence


def relative_strength_index(closes: Sequence[float], period: int) -> Optional[float]:
    """Wilder-smoothed RSI over `period`, evaluated at the last observation.

    Returns None if fewer than `period + 1` observations are available.
    No band is applied to the result here -- this returns the raw 0-100
    value; converting it into points is a B2 scoring decision, not this
    function's job.
    """
    if period <= 0:
        raise ValueError("period must be a positive integer")
    if len(closes) < period + 1:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1 + avg_gain / avg_loss)


def rate_of_change(closes: Sequence[float], lookback: int) -> Optional[float]:
    """Percent change between the last close and the close `lookback`
    bars earlier. Returns None if there are not enough observations.
    """
    if lookback <= 0:
        raise ValueError("lookback must be a positive integer")
    if len(closes) < lookback + 1:
        return None
    prior = closes[-(lookback + 1)]
    if prior == 0:
        return None
    return (closes[-1] / prior - 1.0) * 100.0

"""Corporate-action break detector (design Section 11, decisions 2-4).

Flag only, never adjust: a session is a possible break when
close[t]/close[t-1] is below `low_ratio` or above `high_ratio`. Small
demergers (ratio near 1) are not detected; a corporate-actions feed is v2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class Break:
    index: int  # index of the first bar AFTER the break
    ratio: float


def find_last_break(closes: Sequence[float], low_ratio: float, high_ratio: float) -> Optional[Break]:
    """Most recent break, or None. Non-positive prior closes are skipped."""
    for i in range(len(closes) - 1, 0, -1):
        prior = closes[i - 1]
        if prior <= 0:
            continue
        ratio = closes[i] / prior
        if ratio < low_ratio or ratio > high_ratio:
            return Break(i, ratio)
    return None

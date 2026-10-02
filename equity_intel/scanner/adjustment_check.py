"""Compare daily closes either side of a known split/bonus ex-date.

Pure function, no I/O. It answers one question with numbers only: across
`ex_date`, did the price series move by about 1.0 (the data is already
adjusted for the event) or by about 1 / price_divisor (the data is raw)?

No pass/fail threshold is defined here. Adjacent daily closes move a few
percent on their own, so the caller reads both distances and judges. The
result must never be used to change a scan, a snapshot, or a status.

`price_divisor` is the factor the price is divided by at the ex-date: a
2-for-1 split or a 1:1 bonus is 2; a 10 -> 1 face-value split is 10.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Tuple


@dataclass(frozen=True)
class AdjustmentComparison:
    ex_date: date
    price_divisor: float
    date_before: Optional[date]
    close_before: Optional[float]
    date_on_or_after: Optional[date]
    close_on_or_after: Optional[float]
    observed_ratio: Optional[float]  # close_on_or_after / close_before
    unadjusted_expected_ratio: float  # 1 / price_divisor
    distance_to_adjusted: Optional[float]  # abs(observed_ratio - 1.0)
    distance_to_unadjusted: Optional[float]  # abs(observed_ratio - unadjusted_expected_ratio)
    conclusive: bool  # False when a session is missing on either side of ex_date


def compare_across_event(
    closes: Iterable[Tuple[date, float]],
    ex_date: date,
    price_divisor: float,
) -> AdjustmentComparison:
    if price_divisor <= 1:
        raise ValueError(f"price_divisor must be > 1, got {price_divisor}")
    ordered = sorted(closes, key=lambda pair: pair[0])
    for _, close in ordered:
        if close <= 0:
            raise ValueError(f"non-positive close in series: {close}")

    before = [pair for pair in ordered if pair[0] < ex_date]
    on_or_after = [pair for pair in ordered if pair[0] >= ex_date]
    expected = 1.0 / price_divisor

    if not before or not on_or_after:
        return AdjustmentComparison(
            ex_date=ex_date,
            price_divisor=price_divisor,
            date_before=before[-1][0] if before else None,
            close_before=before[-1][1] if before else None,
            date_on_or_after=on_or_after[0][0] if on_or_after else None,
            close_on_or_after=on_or_after[0][1] if on_or_after else None,
            observed_ratio=None,
            unadjusted_expected_ratio=expected,
            distance_to_adjusted=None,
            distance_to_unadjusted=None,
            conclusive=False,
        )

    date_before, close_before = before[-1]
    date_after, close_after = on_or_after[0]
    observed = close_after / close_before
    return AdjustmentComparison(
        ex_date=ex_date,
        price_divisor=price_divisor,
        date_before=date_before,
        close_before=close_before,
        date_on_or_after=date_after,
        close_on_or_after=close_after,
        observed_ratio=observed,
        unadjusted_expected_ratio=expected,
        distance_to_adjusted=abs(observed - 1.0),
        distance_to_unadjusted=abs(observed - expected),
        conclusive=True,
    )

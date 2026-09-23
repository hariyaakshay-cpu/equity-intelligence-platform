"""Relative volume -- pure math, no usability threshold, no zero-fill."""
from __future__ import annotations

from typing import Optional, Sequence


def relative_volume(
    current_volume: Optional[float], prior_volumes: Sequence[Optional[float]]
) -> Optional[float]:
    """Current volume divided by the mean of `prior_volumes` (current bar
    excluded from the denominator by construction -- the caller passes
    only prior bars).

    Returns None -- NEVER zero -- whenever `current_volume` is missing, any
    `prior_volumes` entry is missing, or the prior set is empty. This
    function does not decide how many of the prior bars must be non-zero
    for volume to be "usable"; that threshold is an unresolved B2/B3
    decision (D19) left to equity_intel/validation/framework.py, which this
    function does not implement.
    """
    if current_volume is None:
        return None
    if not prior_volumes:
        return None
    if any(v is None for v in prior_volumes):
        return None
    denominator = sum(prior_volumes) / len(prior_volumes)
    if denominator == 0:
        return None
    return current_volume / denominator

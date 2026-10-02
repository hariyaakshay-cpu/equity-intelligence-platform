"""Relative return between two series over a shared window -- pure math."""
from __future__ import annotations

from typing import Optional


def relative_return(
    instrument_start: float,
    instrument_end: float,
    benchmark_start: float,
    benchmark_end: float,
) -> Optional[float]:
    """Spread, in percentage points, between an instrument's return and a
    benchmark's return over the same window.

    This function does not select, fetch, or assume any particular
    benchmark (NIFTY 500 or otherwise) -- it operates on whatever two
    price pairs the caller supplies. Which series is "the benchmark" is a
    B3/B2 decision (see B2 spec D03/D04) made outside this function.
    """
    if instrument_start == 0 or benchmark_start == 0:
        return None
    instrument_pct = (instrument_end / instrument_start - 1.0) * 100.0
    benchmark_pct = (benchmark_end / benchmark_start - 1.0) * 100.0
    return instrument_pct - benchmark_pct

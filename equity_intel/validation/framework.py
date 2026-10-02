"""Generic, configuration-driven data-quality checks.

Per the implementation task's examples:
    Allowed:      minimum_history: configuration/input
    Not allowed:  MIN_HISTORY = 252   (unless already authoritative)

`n_bars` (252) is used in the B2 specification for the 52-week window and
the VALID-status minimum, but B2 itself is DRAFT COMPLETE / NOT RELEASED --
not authoritative -- so 252 is not hardcoded here. Every threshold below is
a required, caller-supplied argument with no default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from equity_intel.contracts.market_data import OHLCVObservation


@dataclass(frozen=True)
class ValidationConfig:
    """Every field is an external input. None means "not yet decided" --
    a caller must supply an explicit value to exercise a check; this
    scaffold never supplies one itself."""

    minimum_history_bars: Optional[int] = None
    volume_usable_lookback: Optional[int] = None
    volume_usable_minimum_positive_bars: Optional[int] = None
    require_benchmark: Optional[bool] = None


def has_required_columns(observation: OHLCVObservation) -> bool:
    """Structural check only: does the observation carry the fields the
    B2 specification's Section 3 says are consumed (high, low, close;
    volume optional)? This is a shape check, not a value check."""
    return observation.high is not None and observation.low is not None and observation.close is not None


def has_duplicate_dates(observations: Sequence[OHLCVObservation]) -> bool:
    dates = [o.observation_date for o in observations]
    return len(dates) != len(set(dates))


def is_monotonically_ascending(observations: Sequence[OHLCVObservation]) -> bool:
    dates = [o.observation_date for o in observations]
    return all(dates[i] < dates[i + 1] for i in range(len(dates) - 1))


def has_non_positive_price(observations: Sequence[OHLCVObservation]) -> bool:
    for o in observations:
        for value in (o.high, o.low, o.close):
            if value is not None and value <= 0:
                return True
    return False


def has_inverted_high_low(observations: Sequence[OHLCVObservation]) -> bool:
    return any(o.high is not None and o.low is not None and o.high < o.low for o in observations)


def meets_minimum_history(observations: Sequence[OHLCVObservation], config: ValidationConfig) -> Optional[bool]:
    """Returns None (undecided) if the caller has not supplied
    `minimum_history_bars` -- this function never assumes 252 or any
    other count on its own."""
    if config.minimum_history_bars is None:
        return None
    return len(observations) >= config.minimum_history_bars


def has_usable_volume(
    prior_volumes: Sequence[Optional[float]], current_volume: Optional[float], config: ValidationConfig
) -> Optional[bool]:
    """Returns None (undecided) if the caller has not supplied both
    `volume_usable_lookback` and `volume_usable_minimum_positive_bars` --
    this function never assumes the proposed "15 of 20" rule (D19) on its
    own."""
    if config.volume_usable_lookback is None or config.volume_usable_minimum_positive_bars is None:
        return None
    if current_volume is None:
        return False
    window = prior_volumes[-config.volume_usable_lookback:]
    if len(window) < config.volume_usable_lookback:
        return False
    if any(v is None for v in window):
        return False
    positive_count = sum(1 for v in window if v > 0)
    return positive_count >= config.volume_usable_minimum_positive_bars


def is_stale(latest_observation_date, expected_asof_date) -> Optional[bool]:
    """Returns None if `expected_asof_date` is not supplied -- staleness
    cannot be evaluated without a trading-calendar-derived reference date,
    an unresolved B2/B3 dependency (D18)."""
    if expected_asof_date is None:
        return None
    return latest_observation_date < expected_asof_date

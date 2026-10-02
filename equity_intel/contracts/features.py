"""Raw-feature contract.

Holds the OUTPUT of the pure indicator layer (equity_intel/indicators/)
before any B2 scoring band is applied. Every field is Optional because a
feature may legitimately be unavailable (insufficient history, unusable
volume, missing benchmark) -- per B2's invariant I6, missing data is never
converted to zero or any other default. No field here is a component score;
scores live in scoring.py and are populated only by code this scaffold does
not implement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FeatureSet:
    """Raw, unscored technical features for one instrument as of one date.

    Field names mirror B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md
    Sections 4.1-4.5 ("Features" rows) purely as identifiers for what each
    number IS, not as an endorsement of the periods/windows used to compute
    them (those periods are themselves PROPOSED, see equity_intel/indicators/).
    """

    instrument_id: str
    n_bars: Optional[int] = None
    w52_complete: Optional[bool] = None

    ema_short: Optional[float] = None
    ema_medium: Optional[float] = None
    ema_long: Optional[float] = None
    ema_medium_lag: Optional[float] = None

    rsi: Optional[float] = None
    roc: Optional[float] = None

    relative_return: Optional[float] = None

    relative_volume: Optional[float] = None

    distance_from_high: Optional[float] = None
    prior_high_short: Optional[float] = None
    prior_high_long: Optional[float] = None

    atr_percent: Optional[float] = None

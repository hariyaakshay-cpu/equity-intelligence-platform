"""Scoring contracts -- shapes only, no bands, no cutoff, no K.

Per the implementation task's explicit examples:
    Allowed:      score: Optional[int]
    Not allowed:  score: int = 20
    Allowed:      candidate_cutoff: configuration/input
    Not allowed:  candidate_cutoff = 70
    Allowed:      watchlist_limit: configuration/input
    Not allowed:  WATCHLIST_K = 10

Nothing in this module violates those examples. `ScoringConfig` carries
candidate_cutoff and watchlist_limit as *optional configuration inputs*
with no default value baked in; a caller who does not supply them gets
`None`, not a number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ComponentResult:
    """The outcome of scoring exactly one component (Trend, Momentum,
    Relative Strength, Volume, or Structure/Breakout) for one instrument.

    `score` is None whenever the component could not be legitimately
    computed (per B2 invariant I6); it is never defaulted to 0. The 0-20
    range named in the B2 specification (Section 3, invariant I1) is a
    SOURCE-DERIVED fact this scaffold documents but does not enforce with a
    hardcoded band table -- only the *shape* (an optional integer) is fixed
    here.
    """

    component_name: str
    score: Optional[int] = None
    basis: Optional[str] = None


@dataclass(frozen=True)
class CompositeResult:
    """The outcome of aggregating five ComponentResults for one instrument.

    Whether a missing component makes `composite` None, a partial sum, or
    something else is the unresolved B2 decision D07/D08. This contract
    only records whatever an (unimplemented) aggregator decided; it does
    not decide it. See equity_intel/scoring/interfaces.py.
    """

    instrument_id: str
    components: tuple[ComponentResult, ...] = field(default_factory=tuple)
    composite: Optional[int] = None


@dataclass(frozen=True)
class ScoringConfig:
    """Configuration surface for values that remain unresolved B2 human
    decisions. Every field defaults to None (unset) rather than to any of
    the proposed placeholder values (70, 10, or any band). A caller that
    wants to exercise a proposed value must supply it explicitly and
    externally to this package -- this package never assumes one.
    """

    candidate_cutoff: Optional[int] = None
    watchlist_limit: Optional[int] = None
    score_version: Optional[str] = None

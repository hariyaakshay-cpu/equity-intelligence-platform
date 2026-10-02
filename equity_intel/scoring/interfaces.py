"""ScoreComponent and CompositeAggregator abstractions.

These define INPUTS and OUTPUTS only. Concrete band tables, the composite
aggregation policy, and the candidate cutoff are unresolved B2 decisions
(D01-D05, D07/D08, D11) and are not implemented here.
"""
from __future__ import annotations

import abc

from equity_intel.contracts.features import FeatureSet
from equity_intel.contracts.scoring import ComponentResult, CompositeResult, ScoringConfig


class ScoreComponent(abc.ABC):
    """One of the five B2 components (Trend, Momentum, Relative Strength,
    Volume, Structure/Breakout). A concrete implementation would turn a
    FeatureSet into a ComponentResult using an approved B2 band table --
    no such implementation exists in this scaffold.
    """

    component_name: str

    @abc.abstractmethod
    def compute(self, features: FeatureSet) -> ComponentResult:
        """Must be implemented once the relevant B2 band table (D01-D05)
        is human-approved. Until then, any concrete subclass must raise
        NotImplementedError rather than guess a threshold.
        """
        raise NotImplementedError(
            "B2 scoring thresholds are not yet authoritative "
            "(see B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md, Section 18)"
        )


class CompositeAggregator(abc.ABC):
    """Combines five ComponentResults into a CompositeResult.

    The aggregation policy on a missing component (None-propagate vs.
    partial sum vs. something else) is unresolved B2 decision D07/D08.
    No concrete aggregator exists in this scaffold.
    """

    @abc.abstractmethod
    def aggregate(self, instrument_id: str, components: "tuple[ComponentResult, ...]") -> CompositeResult:
        raise NotImplementedError(
            "B2 composite missing-component policy is not yet authoritative "
            "(see B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md, Section 5, D07/D08)"
        )


class CandidateSelector(abc.ABC):
    """Applies the (unresolved) candidate cutoff to a CompositeResult.

    ScoringConfig.candidate_cutoff carries the configuration input; this
    scaffold never supplies a value for it and never implements the
    comparison.
    """

    @abc.abstractmethod
    def select(self, composite: CompositeResult, config: ScoringConfig) -> bool:
        raise NotImplementedError(
            "B2 candidate cutoff is UNRESOLVED (D11: AUTHORITY: NONE) "
            "(see B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md, Section 10)"
        )

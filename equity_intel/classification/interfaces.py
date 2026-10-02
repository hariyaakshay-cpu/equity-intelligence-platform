"""Classifier abstraction.

No concrete trigger threshold (>=16, <=4, >=12, >=14, >=16, >=12, or any
other B2-proposed value) appears anywhere in this module.
"""
from __future__ import annotations

import abc

from equity_intel.contracts.classification import ClassificationResult
from equity_intel.contracts.scoring import CompositeResult


class Classifier(abc.ABC):
    @abc.abstractmethod
    def classify(self, composite: CompositeResult) -> ClassificationResult:
        raise NotImplementedError(
            "B2 classification triggers are not yet authoritative "
            "(see B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md, Section 8, D10)"
        )

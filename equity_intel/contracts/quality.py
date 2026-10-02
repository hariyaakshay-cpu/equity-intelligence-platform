"""Data-quality/status vocabulary.

Per B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md Section 7 and the
original design-adjudication material (G1), the four data statuses below
are already established governing vocabulary -- not a new business
invention of this scaffold. Per the implementation task's own instruction
(Section C: "Only use status vocabulary already established by the
governing material ... those may be represented structurally"), this is
the one status vocabulary this package freezes as an enum.

The *rules* that assign one of these statuses to an observation (STALE
relative to what calendar, INSUFFICIENT_HISTORY at what bar count, FAILED
under what validation rule) are NOT implemented here -- those rules depend
on unresolved B2/B3 decisions (trading-calendar source, minimum-history
count, volume-usability threshold) and are deliberately left to a
configuration-driven validator (see equity_intel/validation/framework.py).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional


class DataStatus(str, enum.Enum):
    VALID = "VALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE = "STALE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DataQualityResult:
    """The outcome of validating one instrument's observation series.

    `reason` is a free-form string (e.g. a code like DQ_STALE), not a fixed
    enum: the exact reason-code vocabulary and its triggers are still
    PROPOSED -- REQUIRES HUMAN APPROVAL (B2 spec Section 14 / D16) and are
    not frozen by this scaffold.
    """

    status: DataStatus
    reason: Optional[str] = None

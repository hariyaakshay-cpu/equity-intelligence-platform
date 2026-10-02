"""Classification contract -- neutral interface, not a frozen vocabulary.

The classification tag vocabulary (STRONG_TREND, WEAK_TREND, etc.) is
described in the B2 specification as SOURCE-DERIVED from the original
design-adjudication material, but B2 as a whole remains DRAFT COMPLETE /
RELEASE BLOCKED (not authoritative) until human sign-off. Per the
implementation task's own instruction ("If classification vocabulary
remains proposed rather than approved, represent it only as a neutral
interface/type rather than a frozen enum"), this scaffold treats the
vocabulary as NOT YET approved and does not freeze it as an enum. `tags`
and `primary` are free-form strings so that no classification label, and
no trigger threshold that would assign one, is encoded here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ClassificationResult:
    """The outcome of classifying one instrument's scored result.

    Both fields are free-form and default to empty/None. No code in this
    package populates them -- see equity_intel/classification/interfaces.py.
    """

    instrument_id: str
    tags: List[str] = field(default_factory=list)
    primary: Optional[str] = None

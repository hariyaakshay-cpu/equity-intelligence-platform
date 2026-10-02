"""Scan-state vocabulary.

SCORED / ELIGIBLE / CANDIDATE / WATCHLISTED are the state names already
identified by the prior, non-authoritative Equity Intelligence design
material and carried into the B2 specification's state-model section
(Section 9). Per the implementation task's explicit authorization ("if the
architecture identifies: SCORED ELIGIBLE CANDIDATE WATCHLISTED -- these may
be represented structurally"), the STATE NAMES are frozen as an enum here.

The TRANSITIONS between these states are NOT implemented in this module or
anywhere in this package: entry into CANDIDATE depends on the unresolved
B2 candidate cutoff (D11), and entry into WATCHLISTED depends on the
unresolved B2 watchlist size (D12) and the unresolved B2 ranking/tie-break
rule (D14). No function in this package computes a transition.
"""
from __future__ import annotations

import enum


class ScanState(str, enum.Enum):
    SCORED = "SCORED"
    ELIGIBLE = "ELIGIBLE"
    CANDIDATE = "CANDIDATE"
    WATCHLISTED = "WATCHLISTED"

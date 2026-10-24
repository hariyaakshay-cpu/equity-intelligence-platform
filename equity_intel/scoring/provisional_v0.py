"""PROVISIONAL v0 scoring bands. PROPOSED - NOT AUTHORITATIVE (B2 still open).

Source: research/b2_threshold_sensitivity_study_2026-09-22.md, lines 43-47.
Decision record: docs/architecture/equity_intel_scoring_v0_provisional_decision.md.

Each band table is a list of (upper_edge, points) pairs in ascending order,
followed by the points for any value at or above the last edge. Edge
convention (an ASSUMPTION, not in the source): lower edge inclusive, upper
edge exclusive. The one exception is ROC, whose first band is "<= 0".
"""
LABEL = "PROVISIONAL - not B2-authoritative"

# D02 Momentum: RSI14 (0-10) + ROC10 % (0-10)
RSI_BANDS = [(40.0, 0), (50.0, 2), (55.0, 4), (60.0, 6), (70.0, 8)]
RSI_TOP = 10
ROC_FIRST_EDGE_INCLUSIVE = True  # "<= 0 -> 0"
ROC_BANDS = [(0.0, 0), (2.0, 2), (4.0, 4), (6.0, 6), (10.0, 8)]
ROC_TOP = 10

# D01 Trend: five boolean tests x 4 points (0-20); min 200 bars (EMA200 must exist).
# Tests 1-4 are named in the B2 study; the FIFTH (EMA20 > EMA50) is an ASSUMPTION
# because the authoritative spec text is not in the repo. Swap it here if wrong.
TREND_POINTS_PER_TEST = 4
TREND_FIFTH_TEST_IS_ASSUMED = True

# D03 Relative Strength: 60-bar return minus benchmark return, percentage points
RS_BANDS = [(-5.0, 0), (-2.0, 4), (0.0, 8), (3.0, 12), (6.0, 16)]
RS_TOP = 20

# D04 Volume: RVOL20 (current bar excluded from denominator)
RVOL_BANDS = [(0.8, 0), (1.0, 4), (1.5, 8), (2.0, 12), (3.0, 16)]
RVOL_TOP = 20

# D05 Structure (distance part only): % below the 252-bar high. Points DECREASE.
DIST52_BANDS = [(2.0, 12), (5.0, 9), (10.0, 6), (20.0, 3)]
DIST52_TOP = 0

# D05 Structure breakout add-on (prior highs exclude the current bar, use daily highs)
BREAKOUT_MEDIUM_POINTS = 8   # close > 50-bar prior high
BREAKOUT_SHORT_POINTS = 4    # close > 20-bar prior high (only if not above the 50-bar)

# Horizon split (OWNER-APPROVED 2026-10-24, NOT in the B2 spec). Same five components,
# regrouped; each score is shown as a percentage of its own maximum.
#   SHORT  = momentum (20) + volume (20) + breakout add-on (8)            -> max 48
#   MEDIUM = trend (20) + relative strength (20) + 52w-distance part (12) -> max 52
SHORT_MAX = 48
MEDIUM_MAX = 52
HORIZON_CUTOFF_PCT = 70   # placeholder, AUTHORITY: NONE
HORIZON_WATCHLIST_LIMIT = 10  # placeholder, AUTHORITY: NONE

# Placeholders with no source basis (AUTHORITY: NONE)
CANDIDATE_CUTOFF = 70
WATCHLIST_LIMIT = 10

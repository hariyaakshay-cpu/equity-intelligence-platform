# Equity Intelligence: provisional scoring v0 decision

Date: 2026-10-24
Status: APPROVED BY OWNER AS PROVISIONAL (not B2-authoritative)

## 1. Decision

The owner (Akshay) approved on 2026-10-24 building scoring v0 using the
PROPOSED bands recorded in
`research/b2_threshold_sensitivity_study_2026-09-22.md` (decision register,
D01-D05, D07, D11), so that daily candidate signals can be viewed on the
equity dashboard. This does NOT resolve B2. B2 stays OPEN; every value below
is provisional and must be replaced or ratified by an authoritative B2
source document.

## 2. Scope of v0

| ID  | Component / rule          | v0 source (all PROPOSED, NOT AUTHORITATIVE)                          |
|-----|---------------------------|----------------------------------------------------------------------|
| D01 | Trend (0-20)              | EMA 20/50/200, five tests x 4 pts, min 200 bars                      |
| D02 | Momentum (0-20)           | RSI14 bands (0-10) + ROC10 bands (0-10), min 15 bars                 |
| D03 | Relative Strength (0-20)  | 60-bar return vs NIFTY 500, bands 0/4/8/12/16/20                     |
| D04 | Volume (0-20)             | RVOL20 (current bar excluded) bands 0/4/8/12/16/20; usable if >=15 of prior 20 bars have volume > 0 |
| D05 | Structure/Breakout (0-20) | dist52 bands + PH20/PH50 breakout; None when w52_complete = 0        |
| D07 | Composite                 | sum of five components; None if ANY component is None (no partial sum) |
| D11 | Candidate cutoff          | 70 (placeholder, AUTHORITY: NONE)                                    |
| --  | Watchlist limit           | top 10 (placeholder, AUTHORITY: NONE)                                |

Exact band tables are those in the sensitivity study's decision register
(lines 43-47 at the time of writing). They are not restated here so a second
copy cannot drift from the source.

## 3. Rules that stay in force

- A component that cannot be legitimately computed is `None`, never 0 (B2 invariant I6).
- No threshold, cutoff or limit is hardcoded in `equity_intel/contracts/scoring.py`;
  v0 values live in a separate, clearly named provisional config module.
- Every stored score and every dashboard view carries the label
  `PROVISIONAL - not B2-authoritative`; the dashboard `scoring_status`
  changes from `BLOCKED_B2` to `PROVISIONAL_V0`.
- Scores are descriptive model output, not trade advice. The equity side
  sends signals only; the owner places any trades himself.
- No broker, order-placement or paper-engine imports (execution-boundary
  decision unchanged).
- Stage 4 (positive expectancy after costs) has NOT been passed; v0 scores
  make no claim of expectancy.

## 4. Implementation order (each step reviewed as a diff before the next)

1. This decision record.
2. Five component calculations in `equity_intel/scoring/` with tests.
3. Composite and candidate rows persisted to `data/equity_intel.db` (schema change, flagged separately).
4. Dashboard Signals tab (daily).
5. Telegram delivery, after the owner has reviewed the daily output.

Intraday signals remain a separate DRAFT spec and are not part of v0.

## 5. Note on the freeze policy

`docs/development_freeze_policy.md` lives in `algo_trader`, not in this
repository. Whether a matching freeze-policy row is needed here is left to
the owner.

## 6. Short / medium horizon split (added 2026-10-24, owner-approved)

Not part of the B2 spec. The same five components are regrouped; each horizon
score is a percentage of its own maximum, so the placeholder cutoff of 70 means
the same thing for both. Missing part -> None (no partial sum). Same eligibility
rules as the composite (VALID data, no corporate-action break flag).

| Horizon | Parts | Max |
|---------|-------|-----|
| SHORT   | momentum (20) + volume (20) + breakout add-on (8) | 48 |
| MEDIUM  | trend (20) + relative strength (20) + 52-week-distance part (12) | 52 |

Cutoff 70 and top-10 per horizon are placeholders (AUTHORITY: NONE). Neither
horizon has a tested holding period or expectancy; Stage 4 has not been run.
Stored in `e4_provisional_horizons`. Values live in `equity_intel/scoring/provisional_v0.py`.

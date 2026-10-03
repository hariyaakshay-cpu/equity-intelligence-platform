# Equity Intelligence — ML Research Specification

Status: **DRAFT — not approved.** Drafted 2026-10-03; amended 2026-10-03
(Section 5A prerequisites, numeric gate criteria 3–4 in Section 7.4, Section 12
order) and again on review (deterministic calibration bins, Gate 4 edge cases,
price discontinuity vs corporate-action evidence, eligibility hierarchy
5A.5). Nothing in this document
is implemented. Approval by Akshay is required before any code, dataset or
experiment exists. Numbers marked **PROPOSED** are conservative starting values
with their derivation shown; they are for ratification or change, and must not
be tuned after results are seen (Section 9).

## 0. Scope and separation

This specification covers **offline machine-learning research on stored equity
data** and nothing else.

Explicitly **out of scope** — each needs its own separately approved
specification, and this document must not be read as pre-approving any of them:

- **B2 Scoring** (composite score, ranking). Stays `BLOCKED_B2`.
- **Trade Plan** (entry, stop loss, targets T1–T3, risk/reward, invalidation,
  position sizing).
- Any dashboard display of ML *results*, and any ML API route (Section 10 allows
  only the static status tab).
- Order-book / L2 depth features (not persisted; the decoder was not active).
- Intraday data of any kind.

The three tracks are independent. ML results cannot change a B2 rule, a
trade-plan rule, or an existing dashboard number, and none of them may consume
another's output until that dependency is itself specified and approved.

## 1. Frozen rules

ML outputs **cannot**:

1. create, modify or cancel orders, or touch any broker interface;
2. modify positions, or trigger or record paper trades;
3. appear in `/api/equity/candidates`, be used to rank or order symbols there,
   or be added to any existing response;
4. modify, feed or stand in for B2 scores or the `scoring_status` field;
5. generate entry, stop loss, targets or position sizing;
6. be presented anywhere as a trading recommendation, signal or "buy/sell".

Further:

- **Read-only on existing data.** ML code opens the canonical database only
  through `equity_intel.persistence.connection.get_read_only_connection`. It
  never writes to `data/equity_intel.db`; in particular nothing is added to the
  `e4_*`, `scan_*`, `paper_watchlist` or any other existing table.
- **Isolated code.** ML code lives outside `equity_intel/` and `dashboard/`.
  `equity_intel/` and `dashboard/` must not import it, and it must not import
  `dashboard`, scanner writers or execution modules. A static-analysis test, in
  the style of `test_execution_isolation.py` and
  `test_db_connection_boundary.py`, enforces both directions (Section 11).
- **Label everything.** Every ML artefact carries the text
  `RESEARCH ONLY — NOT A TRADING RECOMMENDATION`.

## 2. Current data — formal record

These facts bound what research can establish. They were measured on
2026-10-03 from `data/equity_intel.db` and must be re-measured and re-recorded
at the start of every dataset version.

| Property | Measured value |
|---|---|
| History per symbol | about 252 daily bars (1 year) |
| Date range of bars | 2025-09-23 to 2026-09-29 |
| Symbols | 486 (of a 500-name universe; 14 have no E4 features) |
| Daily observations | 122,472 in the latest acquisition run |
| Benchmark history | 341 sessions, 2025-05-19 to 2026-09-29 |
| Universe | **today's constituents** applied to the past |
| Price adjustment | split-adjusted; **demergers not adjusted** |
| Survivorship | **present** (delisted/removed names absent) |
| Corporate-action info | review CSV is a current snapshot, not point-in-time |
| Calendar | provisional / index-derived, not an exchange calendar |
| Volume | present; delivery, depth, intraday absent |

Consequences recorded as binding:

- Any result on this data is **exploratory**. It cannot support a claim that a
  model works; it can only support the decision to gather more data (Section 8).
- Results will be optimistically biased by survivorship and by the use of
  today's universe. Every report states this.
- One year of data spans, at most, one market regime. Out-of-sample results
  cannot be generalised across regimes.

## 3. Target definition (single target)

Exactly one target is defined for the first phase. No second target (volatility,
ATR barriers, multi-horizon) is added until this one has passed its evidence
gate.

```
forward_5d_return(s, t) = Close(s, t+5) / Close(s, t) - 1
positive_5d(s, t)       = 1 if forward_5d_return(s, t) > 0 else 0
```

- `t` is a trading session of symbol `s`; `t+5` is the fifth following session
  **in the verified trading calendar** (Section 5A.1), not five rows or five
  weekdays. No target is generated until that calendar exists.
- Features for sample `(s, t)` use information available at the close of `t`
  only. The label uses the close of `t+5`. No trade or entry price is implied.
- A sample is **dropped** (never filled) if `Close(s, t)` or `Close(s, t+5)` is
  missing, non-positive, or if any session between them is missing for `s`.
- A zero return is labelled `0`; the zero count is reported.
- Samples whose label window contains an observed break or a known unadjusted
  corporate-action event are **excluded and counted** (Section 5A.5, level E3),
  not silently kept.

## 4. Features (version `features-v1`, deterministic)

Only information at or before `t`. Computed with the existing pure functions in
`equity_intel/indicators/` where one exists, so research features cannot drift
from the dashboard's definitions; new definitions are added here, not ad hoc.

- **Trend:** distance of close from EMA 20/50/200 (percent); EMA slopes.
- **Momentum:** RSI 14, ROC 10, returns over 1, 3, 5, 10, 20 sessions.
- **Structure:** percent below the 252-bar high where a full window exists (else
  missing); percent above the 252-bar low.
- **Volatility / volume:** ATR percent, realised volatility, RVOL 20.
- **Relative:** stock minus benchmark return over 5 and 20 sessions.
- **Context (computed from stored data only):** benchmark trend and volatility,
  universe breadth (share above each EMA) and sector breadth, each computed
  **as of `t`**.

Rules:

- **Missing is missing.** Features lacking enough history are `NaN`/null. No
  zero-fill. How a model handles missing values is part of the experiment
  record, identical across tiers for comparability.
- **Point-in-time.** A feature may use a value only if it would have been
  computable at the close of `t`. In particular the existing E4 break detector
  (`find_last_break`) examines a whole history and therefore uses later bars; it
  must not feed features for earlier `t`. The point-in-time break rule that
  replaces it for research is defined in Section 5A.3.
- **No order-book features.** Excluded until L2 storage exists and is
  separately specified.
- Every feature set has a `feature_version`; changing any definition creates a
  new version and invalidates comparison with earlier results.

## 5. Data limitations that must be handled, not ignored

1. **Demergers unadjusted / splits adjusted by the vendor.** Observed breaks and
   known corporate-action events are handled as set out in 5A.3 and 5A.5
   (feature missingness or exclusion); the count and symbols are listed in the
   experiment record. No manual price patching.
2. **Survivorship and today's constituents.** Cannot be fixed with current data.
   Recorded as a standing limitation; reduced only by a point-in-time
   constituent history (a Section 8 prerequisite for Tiers 3–4).
3. **Future corporate-action knowledge.** The review CSV, adjustment status and
   break flags reflect knowledge from after `t`. They may be used to *exclude
   samples from the study* (an auditing step), never as features.
4. **Calendar.** Session alignment uses only the verified calendar of Section
   5A.1; any symbol/date that cannot be aligned to it is dropped and counted.
5. **Cross-sectional dependence.** Samples on the same date are correlated;
   effective sample size is closer to the number of independent dates than to
   the number of rows. Uncertainty is therefore estimated by resampling dates
   (block bootstrap by date), never rows.

## 5A. Prerequisites before any dataset is built

Each item below produces a recorded, versioned result. No dataset version
(Section 11), and no target or feature value, is produced until 5A.1–5A.3
(including the corporate-action event list in 5A.3) are complete and
approved. 5A.4 records evidence already gathered. 5A.5 fixes how the builder
decides which observations are eligible.

### 5A.1 Verified NSE trading calendar (hard prerequisite)

- **Definition.** `calendar_version` is an explicit, dated list of NSE equity
  cash-market sessions over the dataset span: every weekday that is not an
  exchange holiday, **plus** every special session (Muhurat trading, Budget-day
  Saturdays, live disaster-recovery drill sessions and any other
  exchange-notified session), **minus** any notified closure.
- **Sources.** NSE's published holiday lists and special-session circulars are
  primary. Observed vendor bars are a cross-check only: a vendor bar on a date
  the calendar says is closed, or a calendar session where the benchmark index
  has no bar, is a discrepancy. Every discrepancy is listed and resolved, with
  its source recorded, before the version is approved.
- **Evidence this matters (Section 5A.4).** Upstox returns weekend-dated bars on
  real special sessions (for example 2015-02-28, 2020-02-01, 2024-01-20,
  2024-03-02, 2024-05-18, 2025-02-01). For some symbols those special-session
  bars are missing before 2019 while the index has them. A weekday rule is
  therefore wrong in both directions.
- **Output.** A calendar file with its content hash, the discrepancy list, and
  the sources consulted. Changing the calendar creates a new
  `calendar_version` and a new dataset version.
- **One calendar.** This calendar is meant to become the single authoritative
  calendar for the project, including the dashboard's freshness check, which is
  currently weekday-only and labelled approximate. Changing the dashboard is
  **not** part of this specification: the dashboard is frozen, and adopting the
  calendar there is a separate, separately approved dashboard change.

### 5A.2 Survivorship audit (measured, not only stated)

The dataset universe is today's constituent snapshot
(`data/reference/nifty500_constituents_2026-09-24.csv`). The audit measures how
far that departs from a point-in-time universe over the dataset span
`[D0, D1]`. At minimum it records:

1. **Entrants within the window.** For each current constituent, the date of
   its first available bar. Count and list the constituents whose first bar is
   after `D0` (they entered the market, and therefore the index, inside the
   window).
2. **Membership evidence.** For each symbol, the dates in `[D0, D1]` for which
   there is documentary evidence that it was a Nifty 500 member (an
   index-provider constituent list or reconstitution notice covering that
   date). Count the symbols with **no evidence of full-period membership**.
3. **Proportion affected.** The share of candidate samples `(s, t)` for which
   membership of `s` at `t` is not evidenced, overall and by year.
4. **Reconstructability.** Whether historical membership can be reconstructed
   from available sources (for example, by applying index reconstitution
   notices backwards from the snapshot), recorded as `RECONSTRUCTED`,
   `PARTIAL (<date range>)` or `NOT_RECONSTRUCTABLE`, with sources. It also
   records whether the vendor still serves history for names that left the
   index or were delisted; without that, removed names cannot be added even if
   membership is known.

If membership cannot be reconstructed, the dataset is labelled
`universe: current constituents — NOT point-in-time` and every result carries
that label and the measured proportion from item 3. The current universe is
never described as point-in-time.

### 5A.3 Point-in-time break rule (replaces whole-history detection for research)

The E4 detector `find_last_break` inspects a symbol's whole history and is
therefore forbidden as a source of any research feature or of any value
attached to an earlier `t`. Research uses this rule instead.

Let `t_1 < t_2 < …` be the sessions of symbol `s` in the verified calendar
that have a valid close, and `prev(t)` the latest such session before `t`.

```
r(s, t)      = Close(s, t) / Close(s, prev(t))
is_break(s,t) = r(s, t) < L  or  r(s, t) > H          PROPOSED: L = 0.5, H = 2.0
                                                      (the E4 thresholds, for parity)
last_break(s, t) = the latest t' <= t with is_break(s, t'), else none
```

- `is_break(s, t)` uses only `Close(s, t)` and `Close(s, prev(t))`, both known at
  the close of `t`. `last_break(s, t)` uses only breaks at or before `t`.
- **Feature consequence.** A feature at `t` whose lookback window (the bars it
  reads) includes `last_break(s, t)` or any bar before it is **missing** for
  that `t`; it is computed only from bars strictly after the most recent break.
  `bars_since_break(s, t)` (sessions since `last_break(s, t)`, missing if none)
  may itself be a feature.
- **Prohibited:** reading any bar after `t`; using a break detected later in
  the series; using corporate-action records, adjustment flags or review CSVs
  (all known only later) in any feature; computing a value over the complete
  history and assigning it backwards to earlier dates.
- **Label windows are separate.** Excluding a sample whose label window
  `(t, t+5]` contains a break, or a known corporate action, is an audit step
  that may use later knowledge (Section 5 item 3). It removes samples; it never
  creates a feature value.
- **This is not a corporate-action detector.** Ratio thresholds miss events
  whose price ratio lies inside `[L, H]`; the 2025 Tata Motors demerger
  (`TMPV`) is not detected at 0.5/2.0 (Section 5A.4). The absence of a detected
  break is never evidence that no corporate action occurred.

Two separate concepts are therefore kept apart in every dataset:

1. **Observed price discontinuity** — `is_break(s, t)` above, computed from
   bars only, point-in-time. It may drive feature missingness and
   `bars_since_break`.
2. **Known corporate-action event** — a record from an authoritative
   point-in-time event source (exchange corporate-action announcements, with
   symbol, event type, ex-date, ratio or terms, announcement date, and the
   source). Each event also records whether the vendor's prices are adjusted
   for it (`ADJUSTED`, `UNADJUSTED` or `UNKNOWN`; `UNKNOWN` is treated as
   `UNADJUSTED`). The current review CSV is a snapshot, not such a source, and
   may be used only for events whose ex-date and terms are verified against
   one.

A known `UNADJUSTED` event invalidates observations even when no
discontinuity is detected. It is used only to **exclude** observations
(Section 5A.5, level E3), never to create a feature value. The event list is a
versioned input (`ca_events_version`) built before any dataset version.
- **Truncation-invariance test (mandatory, part of the leakage audit).** For a
  sample of symbols and dates, every feature computed for `(s, t)` from the
  full series must equal the same feature computed from the series truncated
  at `t`. Any difference fails the audit.

### 5A.4 History depth available from the vendor (evidence, 2026-10-03)

A read-only probe (`research/ml/diagnostics/upstox_history_depth_probe.py`;
output and findings in `research/ml/diagnostics/`) fetched Upstox daily history
for six instruments. It wrote nothing to any database.

| Instrument | Role | Earliest | Latest | Sessions |
|---|---|---|---|---|
| RELIANCE | large cap | 2000-01-03 | 2026-10-01 | 6,652 |
| VOLTAS | mid cap | 2003-01-01 | 2026-10-01 | 5,857 |
| SWIGGY | recent listing | 2024-11-13 | 2026-10-01 | 467 |
| VEDL | known break (2026-04-30) | 2003-01-01 | 2026-10-01 | 5,857 |
| TMPV | demerged (former Tata Motors ISIN) | 2000-01-03 | 2026-10-01 | 6,606 |
| Nifty 500 | benchmark | ≤ 1996-01-01 (probe floor) | 2026-10-01 | 7,636 |

- A request spanning more than ten years is refused (HTTP 400); history must be
  fetched in decade windows.
- Depth is not the binding constraint for long-listed names: 20+ years are
  available, against the 8 years Tier 4 requires. Recent listings are
  inherently short, which is a survivorship question (5A.2), not a vendor limit.
- Data-quality findings for the audit (Section 5): a 33-day hole
  (2004-05-21 to 2004-06-23) in VOLTAS, VEDL and TMPV but not RELIANCE; missing
  pre-2019 special-session bars for the same three; two consecutive VEDL close
  jumps in January 2005 (×3.22, ×2.48) that look like a vendor or
  corporate-action artefact.
- Six instruments are a sample, not an audit. Full-universe depth is measured
  during historical data expansion (Section 12).

### 5A.5 Observation eligibility hierarchy

Every candidate observation `(s, t)` passes through these levels **in this
order**. The first level it fails assigns its single exclusion reason; later
levels are not evaluated for it. The dataset builder may not reorder, skip or
add levels, and may not decide a case these rules do not cover: an uncovered
case stops the build and requires an amendment to this section.

| Level | Check | Exclusion reason codes |
|---|---|---|
| E1 Calendar | `t` is a session in `calendar_version`; `s` has a valid bar (positive OHLC, high ≥ low) at `t` and at `prev(t)`. Vendor bars on non-sessions are dropped and listed as calendar discrepancies. | `NOT_A_SESSION`, `BAR_MISSING`, `BAR_INVALID` |
| E2 Universe / membership | `s` is in the dataset universe, and its membership at `t` is treated according to the 5A.2 result (below). | `NOT_IN_UNIVERSE`, `MEMBERSHIP_UNEVIDENCED` |
| E3 Corporate action / break | No known `UNADJUSTED` (or `UNKNOWN`) corporate-action event has an ex-date in the feature lookback window `[t − W_max, t]` or the label window `(t, t+5]`. No observed discontinuity (5A.3) lies in the label window. No unresolved vendor data anomaly is listed for `s` over those windows. | `CA_EVENT_IN_WINDOW`, `BREAK_IN_LABEL_WINDOW`, `DATA_ANOMALY` |
| E4 History sufficiency | At least `W_max` valid sessions of `s` exist at or before `t`, and no calendar session in `[t − W_max, t]` lacks a bar for `s`. **PROPOSED:** `W_max = 252` (the longest `features-v1` lookback). | `INSUFFICIENT_HISTORY`, `GAP_IN_LOOKBACK` |
| E5 Feature completeness | Every feature that `features-v1` marks `required` is present. Features not marked required may be missing (Section 4); the `required` list is fixed in the feature version before any build. | `REQUIRED_FEATURE_MISSING` |
| E6 Target availability | The Section 3 label conditions hold: `Close(s, t+5)` valid, and no session between `t` and `t+5` missing for `s`. | `TARGET_UNAVAILABLE` |
| E7 Leakage audit | Dataset-level, not per observation: the Section 11 audit (including truncation invariance) passes. A failure makes the **whole dataset version** ineligible. | `DATASET_LEAKAGE_FAIL` |

An observation that passes E1–E6 in a dataset that passes E7 is an **eligible
ML observation**. Nothing else is.

Rules attached to the hierarchy:

- **Membership treatment (E2)** is fixed per dataset version from the 5A.2
  result. **PROPOSED:** if `RECONSTRUCTED` or `PARTIAL`, observations whose
  membership is not evidenced are excluded as `MEMBERSHIP_UNEVIDENCED` (this
  may shorten the usable span); if `NOT_RECONSTRUCTABLE`, they are retained and
  the whole dataset carries the label `current constituents — NOT
  point-in-time` with the measured affected share.
- **Breaks in the lookback window** are not an E3 exclusion: they make the
  affected features missing (5A.3), which E5 then judges. Breaks in the label
  window are excluded at E3.
- **Data anomalies** (for example the 2004 vendor hole or the VEDL 2005 jumps)
  are listed in the data-quality audit with an explicit status. A hole is
  handled by E4 (`GAP_IN_LOOKBACK`) and E6. An unresolved price anomaly
  excludes the affected windows at E3 (`DATA_ANOMALY`); prices are never
  patched.
- **Reporting.** Every dataset version records the count of observations
  excluded at each level and reason code, overall and by year and sector, and
  the count of eligible observations. These counts are part of the dataset
  manifest and of every experiment report built on it.

## 6. Validation protocol (frozen)

Prohibited:

- random train/test or random k-fold splits;
- any feature, label or normaliser that uses data after the split's training
  end (scalers, imputers, winsorisation limits, feature selection and
  hyper-parameters are fitted on training data only);
- using future corporate-action information as a feature;
- overlapping labels straddling a boundary between training, validation or test.

Required structure:

```
TRAIN → EMBARGO → VALIDATION → EMBARGO → TEST (out of sample)
```

- **Embargo ≥ the label horizon (5 sessions)**, applied by date across all
  symbols (a sample whose `[t, t+5]` window overlaps the next segment is
  removed). PROPOSED: use 10 sessions (2 × horizon) to cover calendar
  uncertainty.
- **Walk-forward:** expanding training window, successive test blocks, each fold
  using the same embargo. PROPOSED: test blocks of about 20 sessions (one
  month), so a year of data yields only a handful of folds — stated as a
  limitation, not hidden.
- The final **TEST block is untouched** until the model, features and
  hyper-parameters are frozen for that experiment. It is evaluated once.
  Re-evaluating on it after changes makes it validation data; a new,
  later test block is then required.
- Splits are defined by **dates**, recorded in the experiment record, identical
  for every model compared.

## 7. Model ladder and evidence gates

```
Tier 0 Historical baseline  → Evidence Gate
Tier 1 Logistic regression  → Evidence Gate
Tier 2 Tree-based model     → Evidence Gate
Tier 3 Neural network       → Evidence Gate
Tier 4 Temporal / deep model
```

**No tier may be implemented merely because it is technically available.**
A tier is started only after (a) the data gate for that tier (Section 8) is
met and recorded, and (b) the preceding tier's evidence gate has been passed
and the pass recorded and approved.

### 7.1 Tier 0 — baselines

- Classification: the training-period share of `positive_5d`.
- Regression: the training-period mean `forward_5d_return`.
- Reported with the same metrics as every other model. If a model cannot beat
  these out of sample, it has no demonstrated value.

### 7.2 Tier 1 — logistic regression

- Predicts `P(positive_5d)`; fixed, small, documented feature set; standardised
  with training-only statistics; regularisation chosen on validation only.
- Chosen first because it is interpretable and hard to over-fit.

### 7.3 Metrics (all reported with date-block bootstrap intervals)

- Classification: AUC, log loss, Brier score, calibration table.
- Regression diagnostic: MAE and out-of-sample R² **relative to the Tier 0 mean
  baseline** (can be negative).
- Per-date cross-sectional rank correlation (information coefficient) as a
  **diagnostic of predictive association only** — it is not a ranking output
  and is never displayed as one.
- Stability: metric by fold, and by sector.
- **No return, P&L, hit-rate-of-trades, Sharpe or drawdown figures.** There are
  no trades in this specification.

### 7.4 Evidence gate (defined before any result is seen)

A tier passes only if **all** hold on the untouched TEST block(s):

1. **PROPOSED:** the lower 95% date-block-bootstrap bound of AUC exceeds 0.50
   **and** log loss is lower than the Tier 0 baseline's, with the lower bound of
   the improvement above 0.
2. **PROPOSED:** the model beats baseline in at least 70% of walk-forward folds
   (with so few folds, a simple majority could be luck; 70% is a conservative
   bar, to be revisited when more folds exist).
3. **PROPOSED — calibration:** maximum absolute calibration error ≤ 0.10,
   defined below.
4. **PROPOSED — concentration:** no single sector and no single walk-forward
   test fold accounts for more than 50% of the aggregate improvement over
   baseline, defined below.
5. Leakage audit passes (Section 11).
6. The conclusion text was written, as a template, before the run.

The thresholds in criteria 1–4 are part of this specification, not of any
experiment's protocol. An experiment cannot choose or adjust them; changing one
is an amendment to this document made before the experiments it governs
(Section 9). Criteria 3 and 4 are defined as follows, over the pooled samples
`i = 1…N` of all walk-forward test folds, with `p_i` the model's predicted
`P(positive_5d)` and `y_i` the label.

**Criterion 3 — maximum absolute calibration error (MACE).**

```
Order the N test samples deterministically by the key
    (p_i ascending, symbol ascending, date t ascending)
where p_i is the stored prediction (float64, as written to the results file).
Let j = 0…N−1 be a sample's position in that order. With K = 10:
    bin(j) = floor(j · K / N)                 (bins 0…9; sizes differ by at most 1)
Ties in p_i never decide a bin: the (symbol, date) key does.
For each bin b:   p̄_b = mean of p_i in b,   ȳ_b = mean of y_i in b
MACE = max over b of | p̄_b − ȳ_b |
Pass if MACE ≤ 0.10.
```

- This is a pass/fail criterion, not a tuning target. Any calibration step
  (for example Platt scaling) is part of the model, fitted on training or
  validation data only, and declared in the pre-registered protocol. Nothing is
  fitted or re-binned on test data.
- The per-bin table (`p̄_b`, `ȳ_b`, count) is reported in full, not only the
  maximum.

**Criterion 4 — concentration of improvement.** Improvement is measured in
log loss against the Tier 0 baseline, whose prediction for every test sample is
the training-period share `π` of `positive_5d` for that fold.

```
ℓ(p, y)  = −[ y·ln(p) + (1−y)·ln(1−p) ],  p clipped to [1e−6, 1 − 1e−6]
d_i      = ℓ(π_fold(i), y_i) − ℓ(p_i, y_i)       per-sample improvement
D        = Σ_i d_i                               aggregate improvement
C_g      = Σ_{i ∈ g} d_i                         contribution of group g
share_g  = C_g / D                               (defined only when D > 0)

Groups g are (a) each eligible sector group and (b) each walk-forward test
fold (definitions below).
Pass if D > 0 and share_g ≤ 0.50 for every sector group and every fold.
```

Equivalent reading: removing any single group must leave at least half of the
net improvement (`D − C_g ≥ D / 2`).

Edge cases, fixed now so no experiment decides them:

- **`D = 0` or `D < 0`.** Criterion 4 **fails**. Shares are not computed and
  are reported as `UNDEFINED (D ≤ 0)`. (Criterion 1 fails in this case too.)
- **Groups that make the result worse (`C_g < 0`).** They stay in the
  calculation. The denominator is the **net** improvement `D`, so a losing group
  shrinks `D` and raises the other groups' shares; the rule becomes stricter,
  never looser. Example: sector A contributes +100 and sector B −60, so
  D = 40 and share_A = 2.5, which fails, because the net result depends wholly
  on A. A negative share satisfies `≤ 0.50` on its own. Every group with
  `C_g < 0` is listed in the report.
- **Small sectors.** A sector with fewer than `n_min` test samples is not
  dropped. It is pooled with all other small sectors into one group,
  `SMALL_SECTORS`, which is tested like any sector. **PROPOSED:**
  `n_min = max(500, 0.01 · N)`. Symbols with no sector in the dataset's mapping
  form the group `UNMAPPED`, which follows the same size rule.
- **Folds.** Every walk-forward test fold is its own group; folds are never
  pooled. With two folds, one of them always holds at least half the
  improvement, so the fold condition says nothing. An experiment with fewer
  than three test folds therefore cannot pass the gate.
- Shares are sums, not averages, so a group's weight reflects its number of
  samples as well as its per-sample improvement. The report gives, for every
  group: sample count, `C_g`, `share_g`, and mean `d_i`.

Passing a gate permits only the **next research step**. It does not permit any
product use. A failed gate means *stop or revise*; a revision is a new
experiment with a new identifier, and every failed experiment is retained.

## 8. Minimum-data gates by tier

The numbers are **PROPOSED**. Derivation: with a 5-session label, a year of
history gives about 50 non-overlapping windows per symbol, and same-date samples
are strongly correlated, so independent information grows with *time*, not
with symbol count. More history, spanning more than one regime, is therefore the
binding constraint.

| Tier | Data requirement (all must hold and be documented) |
|---|---|
| 0 Baseline | current dataset allowed |
| 1 Logistic | current dataset allowed; results labelled exploratory |
| 2 Tree-based | ≥ 3 years (≥ 750 sessions) contiguous daily history for ≥ 400 symbols; benchmark over the same span; completed data-quality audit (Section 5 items 1, 4); evidence gate passed at Tier 1 |
| 3 Neural network | ≥ 5 years (≥ 1,250 sessions) as above; **point-in-time constituent history** (or a documented, quantified survivorship bound); demerger handling verified; Tier 2 gate passed |
| 4 Temporal / deep | ≥ 8 years (≥ 2,000 sessions) contiguous, covering multiple regimes; point-in-time universe; sequence-length and window leakage design approved; Tier 3 gate passed |

If a gate cannot be met, the tier is not started. Thresholds may be changed
only by amending this specification **before** the experiments they govern.

## 9. Pre-registration and anti-tuning

Before an experiment runs, a protocol file is committed that fixes: target,
features, model class and its hyper-parameter search space, split dates,
embargo, metrics, evidence-gate thresholds and the conclusion template. Results
are then produced by running that committed protocol at a recorded commit.

- No threshold, split date, feature, metric or exclusion rule is changed after
  looking at test results; doing so creates a new, separately identified
  experiment.
- The number of experiments run against the same test block is recorded;
  repeated use lowers the credibility of a pass and is stated in the report.

## 10. No dashboard yet

No ML results are shown anywhere, and no ML route or API field exists. No empty
metric tables, illustrative numbers, predictions, probabilities or rankings.

**Amendment (2026-10-03, requested by Akshay):** the dashboard may carry a
**static research-status tab** and a **static gated-items tab**. Their content is
limited to: the programme status text; the model ladder with each tier marked
`NOT RUN` or `GATED`; "Model evaluation" and "Feature analysis" marked
`NOT AVAILABLE`; and the stored-history depth measured from the database (this
single figure rides on the existing `/summary` response as `history`). They
read nothing else, add no route, and must preserve every rule in Section 1.
Tier statuses change only by editing the page text after the corresponding
experiment exists and is approved.

The first real deliverable remains an offline experiment report (Section 13).
Only after at least one gate has been passed and the result reviewed is a
dashboard specification for ML *results* considered.

## 11. Reproducibility, store and isolation

Research artefacts live outside `equity_intel/` and `dashboard/`:

```
research/ml/
    specification/   protocols and this spec's amendments
    datasets/        dataset manifests (hashes); large files git-ignored
    experiments/     one folder per experiment_id
    models/          fitted models (git-ignored; hash recorded)
    results/         reports and metric tables
    diagnostics/     leakage audits, data-quality audits, drift checks
```

Every experiment records, in a machine-readable file:

```
experiment_id            dataset_version        universe_version
feature_version          target_definition      validation_protocol
model_version            code_commit (+ dirty)  run_timestamp
random_seed              library_versions       source_db_sha256
acquisition_run_id       e4_scan_id (if used)   split_dates / embargo
exclusions (counts)      protocol_file_hash
```

- A dataset is built once, exported as an immutable file with a content hash,
  and experiments read that file, not the live database. Identical inputs and
  seed must reproduce identical results.
- **Leakage audit** (a mandatory diagnostic per dataset version): shuffled-label
  test (a model must score ≈ chance), feature-time-stamp test (no feature uses
  data after `t`), truncation-invariance test (Section 5A.3), and split-overlap
  test (no label window crosses a boundary).
  A failed audit blocks all results from that dataset.
- **Isolation tests** (to be written with the first code): ML code does not
  import `dashboard`, scanner writers or execution code; `equity_intel/` and
  `dashboard/` do not import ML code; ML code opens only read-only connections;
  no ML code path references an order, broker or position interface.

## 12. Progression

```
1. This specification (with amendments) — reviewed and approved   ← current step
2. Verified NSE trading calendar (5A.1)
3. Survivorship audit (5A.2)
4. Point-in-time feature rules confirmed, including the break rule and the
   corporate-action event list (5A.3)
5. History-depth result (5A.4; sample probe done, full universe pending)
6. Dataset design (historical data expansion; data-quality audit, Section 5)
7. Dataset v1 + leakage audit
8. Tier 0 baseline          → report
9. Tier 1 logistic          → report → Evidence Gate
10. Decision: stop / revise / continue to Tier 2 (data gate permitting)
```

No expanded data is collected for ML before step 6. Steps 2–7 are
prerequisites for trustworthy results even at Tiers 0–1; running
Tiers 0–1 on the current one-year data is permitted only as an exploratory
dry-run of the pipeline, labelled as such.

## 13. First deliverable shape (illustrative structure, not results)

```
Experiment: ML-BASELINE-001          Status: EXPLORATORY (1-year data)
Target: positive_5d / forward_5d_return
Dataset: <dataset_version, hash>     Universe: <universe_version> (survivorship: present)
Train / Embargo / Validation / Test: <dates>
Tier 0: <log loss, Brier, MAE>       Tier 1: <AUC (CI), log loss (CI), Brier, MAE, R² vs baseline>
Per-fold table · per-sector table · calibration table
Leakage audit: <pass/fail>
Gate result: <pass/fail per criterion, from the pre-registered template>
Conclusion: <pre-registered template text only>
```

Values appear only when produced by a run; none are filled in by hand.

## 14. Approval checklist

- [ ] Section 1 frozen rules accepted
- [ ] Target and feature versions accepted
- [ ] Validation protocol and embargo accepted
- [ ] Tier ladder and PROPOSED gate numbers ratified or amended, including
      MACE ≤ 0.10 and the 50% concentration limit (Section 7.4)
- [ ] Verified-calendar requirement and its sources accepted (5A.1)
- [ ] Survivorship audit measurements accepted (5A.2)
- [ ] Point-in-time break rule and PROPOSED thresholds L = 0.5, H = 2.0
      accepted, with the separate corporate-action event source (5A.3)
- [ ] Observation eligibility hierarchy accepted, including PROPOSED
      `W_max = 252` and the membership treatment (5A.5)
- [ ] Deterministic calibration binning and the Gate 4 edge-case rules,
      including PROPOSED `n_min = max(500, 0.01 · N)`, accepted (Section 7.4)
- [ ] Research store location accepted
- [ ] Confirmed: B2 Scoring and Trade Plan remain separate and out of scope

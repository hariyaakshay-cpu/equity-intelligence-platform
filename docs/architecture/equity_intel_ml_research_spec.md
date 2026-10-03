# Equity Intelligence — ML Research Specification

Status: **DRAFT — not approved.** Drafted 2026-10-03. Nothing in this document
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
  **in the verified trading calendar**, not five rows or five weekdays.
- Features for sample `(s, t)` use information available at the close of `t`
  only. The label uses the close of `t+5`. No trade or entry price is implied.
- A sample is **dropped** (never filled) if `Close(s, t)` or `Close(s, t+5)` is
  missing, non-positive, or if any session between them is missing for `s`.
- A zero return is labelled `0`; the zero count is reported.
- Samples whose window contains a detected corporate-action break (Section 5)
  are **excluded and counted**, not silently kept.

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
  must not feed features for earlier `t`. A point-in-time break rule, run
  bar-by-bar, is defined in the dataset specification before any dataset is
  built.
- **No order-book features.** Excluded until L2 storage exists and is
  separately specified.
- Every feature set has a `feature_version`; changing any definition creates a
  new version and invalidates comparison with earlier results.

## 5. Data limitations that must be handled, not ignored

1. **Demergers unadjusted / splits adjusted by the vendor.** Detected breaks are
   handled by exclusion of affected samples (Section 3); the count and symbols
   are listed in the experiment record. No manual price patching.
2. **Survivorship and today's constituents.** Cannot be fixed with current data.
   Recorded as a standing limitation; reduced only by a point-in-time
   constituent history (a Section 8 prerequisite for Tiers 3–4).
3. **Future corporate-action knowledge.** The review CSV, adjustment status and
   break flags reflect knowledge from after `t`. They may be used to *exclude
   samples from the study* (an auditing step), never as features.
4. **Calendar.** Session alignment relies on the provisional calendar; any
   symbol/date that cannot be aligned is dropped and counted.
5. **Cross-sectional dependence.** Samples on the same date are correlated;
   effective sample size is closer to the number of independent dates than to
   the number of rows. Uncertainty is therefore estimated by resampling dates
   (block bootstrap by date), never rows.

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
3. Calibration is not grossly wrong (a pre-declared maximum calibration error,
   to be fixed in the experiment protocol).
4. The result is not driven by one sector, one date range or one fold
   (reported, with a pre-declared dominance limit).
5. Leakage audit passes (Section 11).
6. The conclusion text was written, as a template, before the run.

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
  data after `t`), and split-overlap test (no label window crosses a boundary).
  A failed audit blocks all results from that dataset.
- **Isolation tests** (to be written with the first code): ML code does not
  import `dashboard`, scanner writers or execution code; `equity_intel/` and
  `dashboard/` do not import ML code; ML code opens only read-only connections;
  no ML code path references an order, broker or position interface.

## 12. Progression

```
1. This specification — approved                        ← current step
2. Historical data expansion (separate task; its own audit)
3. Data-quality audit (Section 5), recorded
4. Dataset v1 + leakage audit
5. Tier 0 baseline          → report
6. Tier 1 logistic          → report → Evidence Gate
7. Decision: stop / revise / continue to Tier 2 (data gate permitting)
```

Steps 2–4 are prerequisites for trustworthy results even at Tiers 0–1; running
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
- [ ] Tier ladder and PROPOSED gate numbers ratified or amended
- [ ] Research store location accepted
- [ ] Confirmed: B2 Scoring and Trade Plan remain separate and out of scope

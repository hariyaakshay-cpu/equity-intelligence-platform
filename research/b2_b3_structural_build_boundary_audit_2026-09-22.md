# B2/B3 Structural Build Boundary Audit
Date: 2026-09-22
Status: READ-ONLY / GOVERNANCE AUDIT

## 1. Governance State
B1: PASS (commit `03ccce95ff47af479d9382723ae91694d39fb6a2`)
B2: DRAFT COMPLETE. B2 RELEASED: NO. B2 authoritative thresholds: NO. B2 human approval: REQUIRED.
B3: BLOCKED. B3 RELEASED: NO.
Paper trading only. No live trading. No production execution changes.
Equity Intelligence implementation: NOT STARTED (verified in Section 3 below — `equity_intel/`, `scripts/equity_scan.py`, `data/equity_intel.db` all absent from the repository).

## 2. Sources Examined

SOURCE AVAILABILITY
-------------------
B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md:
  STATUS: FOUND (session output area, `/mnt/user-data/outputs/`; not a repository file — B2 is explicitly not released into the repo)
  USED FOR: enumerating every proposed numerical threshold and the B2 decision register (D01-D19)
  MATERIAL TO DECISION: YES

B2_SCORING_THRESHOLD_ADJUDICATION_2026-09-21.md:
  STATUS: FOUND (session output area, `/mnt/user-data/outputs/`)
  USED FOR: confirming no authoritative threshold source exists anywhere and the original 17-item unresolved list
  MATERIAL TO DECISION: YES

research/b2_threshold_sensitivity_study_2026-09-22.md:
  STATUS: FOUND (repository, `research/`)
  USED FOR: confirming the repository lacks NIFTY 500 equity/benchmark/volume/sector data needed to empirically test B2
  MATERIAL TO DECISION: YES

docs/development_freeze_policy.md:
  STATUS: FOUND (repository)
  USED FOR: the current freeze-policy state and the exact text of the 2026-09-21 B1 exception row (scope, constraints, forbidden imports, no-modification list)
  MATERIAL TO DECISION: YES

B1 governance exception (commit):
  STATUS: FOUND — commit `03ccce95ff47af479d9382723ae91694d39fb6a2` is HEAD; content matches the freeze-policy row read above
  USED FOR: confirming B1 PASS and the exact approved scope
  MATERIAL TO DECISION: YES

EQUITY_INTELLIGENCE_DESIGN_ADJUDICATION_2026-09-21.md (previously adjudicated architecture/design material):
  STATUS: FOUND (session output area, `/mnt/user-data/outputs/`; not a repository file — it is proposals only, explicitly non-authoritative per its own header)
  USED FOR: the architecture claims verified in Section 3
  MATERIAL TO DECISION: YES

Repository structure (`dashboard/app.py`, `core/database/`, `core/oms/execution_mode.py`, `config/`, and a check for `equity_intel/`, `scripts/equity_scan.py`, `data/equity_intel.db`):
  STATUS: FOUND (all inspected paths exist except the three Equity Intelligence artifacts, which are confirmed absent — see Section 3)
  USED FOR: verifying the current dashboard route pattern, existing database/repository conventions, the execution-mode mechanism to be reused, and that no implementation has begun
  MATERIAL TO DECISION: YES

MISSING-SOURCE IMPACT:
No required source is MISSING, INACCESSIBLE, or AMBIGUOUS. All six inputs the task named were located and read (three in the session output area, since B2's own text states it is deliberately kept outside the repository until released; three in the repository). No conclusion in this audit rests on a missing source, and no source's absence changes the final boundary decision.

## 3. Existing Equity Intelligence Architecture

Verified against the actual repository (not assumed from the design proposal):

| Architectural claim | Verified state |
|---|---|
| `equity_intel/` isolated top-level package | NOT PRESENT. `equity_intel` does not exist in the repository. Proposed only. |
| `scripts/equity_scan.py` standalone scanner | NOT PRESENT. Does not exist. Proposed only. |
| `data/equity_intel.db` separate persistence database | NOT PRESENT. Does not exist. Proposed only. |
| Equity Intelligence must remain separate from the options trading engine | Stated as a constraint in the freeze-policy exception row (docs/development_freeze_policy.md, 2026-09-21 row); not yet enforced by any code, because no code exists. |
| Must not become an execution path | Stated as a constraint in the same row ("no live order, no paper order, no broker call, no OMS write"). Not yet enforced by code — nothing to enforce it in, since no implementation exists. |
| Paper watchlist is the terminal boundary | Stated as a constraint ("The only permitted handoff is the `paper_watchlist` table"). `paper_watchlist` table does not exist yet (no `data/equity_intel.db`, no schema). |
| Must not create engine positions/orders | Stated as a constraint. No code exists yet to violate or honor it. |
| Existing OMS/trading databases must not be reused | Stated as a constraint ("explicit guard refusing `oms_state.db`, `oms_shadow.db` and `production_trading.db`"); the guard itself does not exist yet (no `data/equity_intel.db`, no guard code). |
| Existing options `config/symbols.py` must not become the NIFTY 500 universe authority | `config/symbols.py` was inspected: it defines exactly three index instruments (`NIFTY`, `BANKNIFTY`, `SENSEX`) for the options system. It contains no NIFTY 500 constituent data and could not currently serve as a universe source even if repurposed. Consistent with the constraint, but the constraint is a design statement, not (yet) an enforced rule, since B3 has not been touched. |
| No scheduler is required for the initial scanner architecture | Stated in the design material only (not in the freeze-policy row, which does not mention a scheduler). No scheduler code exists in the repository related to equity scanning. |
| Dashboard additions must be additive and must not alter Page 1 behavior | Freeze-policy row explicitly lists Page 1's four existing routes (`/`, `/run/<action>`, `/api/status`, `/api/symbols`) as preserved, and specifies four new additive routes (`/equity`, `/api/equity/summary`, `/api/equity/candidates`, `/api/equity/sectors`, `/api/equity/stock/<symbol>` — five listed, "Page 2" collectively). `dashboard/app.py` currently has none of the five new routes; only the four existing Page 1 routes were found. |
| Import boundaries must be testable | Freeze-policy row lists a forbidden-import set (`brokers.*`, `core.paper_engine`, `core.continuous_engine`, `core.execution_engine`, `core.oms.order_router`, `core.oms.execution_service`, `core.oms.paper_oms_adapter`, `core.oms.db`, `core.risk_manager`, `strategies.*`, `main`, `core.historical_data`) and says it is "enforced by static import-boundary tests." No such tests exist yet, because there is no `equity_intel/` package for them to test against. |
| System must remain PAPER TRADING ONLY | The freeze-policy row specifies reuse of the existing `core.oms.execution_mode` mechanism (no new trading-mode flag) and that the scan must raise `RuntimeError` if process mode is LIVE. `core/oms/execution_mode.py` exists and was confirmed present; no equity-scan code exists yet to call it. |

**Finding:** every architectural claim in the design material is presently a *stated constraint in an approved governance document* (the B1 freeze-policy exception), not yet an *enforced property of code*, because zero Equity Intelligence code exists. This distinction matters throughout the rest of this audit: "the architecture requires X" is not the same as "X exists and is verified."

## 4. B2 Dependency Analysis

B2 DEPENDENCY: Component scoring (Trend, Momentum, Relative Strength, Volume, Structure/Breakout — the actual numeric bands, EMA periods, RSI/ROC bands, RVOL bands, dist52 bands)
WHY: Every band, period, and point value in D01–D05 of the B2 spec is PROPOSED — REQUIRES HUMAN APPROVAL; none is authoritative.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES — a function/class signature (`def compute_trend(bars) -> int | None`) can exist as a typed stub with no implementation, or an interface documenting required inputs and the 0-20 output contract, without choosing any EMA period or band.

B2 DEPENDENCY: Score ranges (0-20 per component)
WHY: The 0-20 per-component range is SOURCE-DERIVED (from the original design-adjudication prompt, G1), not a new proposal — this is the one numeric fact in B2 that is already governance-approved.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES — and in this one case a type constraint (`int` in `0..20` or `None`) can be encoded directly, since the range itself is already authoritative, though the value-producing logic behind it still cannot be.

B2 DEPENDENCY: Numerical bands (all six band tables: RSI, ROC10, rp60, RVOL, dist52, plus the PH20/PH50 breakout step)
WHY: Every band boundary and point value is PROPOSED — REQUIRES HUMAN APPROVAL (B2 spec Sections 4.1-4.5).
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES — a "band table" data structure/schema can be defined generically (ordered list of (lower, upper, points) tuples) without populating it with the proposed numbers; populating it with the proposed numbers would not be neutral.

B2 DEPENDENCY: Composite calculation (sum of five components)
WHY: `composite = trend + momentum + rs + volume + structure` is SOURCE-DERIVED (G2, the frozen invariant); this rule, uniquely among the numeric content of B2, is already authoritative.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES — and here the sum rule itself could arguably even be implemented as code, since it is not a proposal; but it cannot be exercised meaningfully without the (unapproved) components feeding it, so a functional composite calculator would still have nothing valid to sum.

B2 DEPENDENCY: Missing-component behavior (composite = None if any component missing)
WHY: This is PROPOSED — REQUIRES HUMAN APPROVAL (B2 spec Section 5, D07) — a design choice made among three alternatives with no source basis.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: NO — a composite-aggregation function has to choose *some* behavior when a component is missing (None-propagate, partial-sum, or reject) the moment it is implemented; there is no neutral third option once code exists. A signature that merely returns `Optional[int]` is neutral; a function body that decides what happens on a `None` input is not.

B2 DEPENDENCY: Classification (vocabulary, per-tag triggers, primary-tag precedence)
WHY: The vocabulary (STRONG_TREND, WEAK_TREND, etc.) is SOURCE-DERIVED (G1); the specific trigger thresholds (>=16, <=4, >=12, >=14, >=16, >=12) and the two-field representation are PROPOSED — REQUIRES HUMAN APPROVAL (B2 spec Section 8, D10).
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES for the enum of tag names (already governance-approved vocabulary) and the shape of the two persisted fields; NO for any code that actually assigns a tag from a component score, since that requires the unapproved trigger thresholds.

B2 DEPENDENCY: Candidate cutoff (composite >= 70)
WHY: PROPOSED — REQUIRES HUMAN APPROVAL, and explicitly flagged in the B2 spec's own decision register as `AUTHORITY: NONE`, `STATUS: UNRESOLVED` (D11) — the one item in B2 with zero evidentiary basis of any kind, not even a proposed rationale.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES for a generic `candidate_cutoff: int` configuration field with no default value baked into code or schema; NO for any hardcoded `>= 70` comparison or a database default of 70.

B2 DEPENDENCY: Candidate state (SCORED -> ELIGIBLE -> CANDIDATE -> WATCHLISTED)
WHY: The state names and their conceptual order are PROPOSED (B2 spec Section 9, D13); the transition conditions embed the unapproved cutoff and K values.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES for a state enum with no transition logic; NO for any code implementing a transition, since every transition after SCORED references an unapproved number.

B2 DEPENDENCY: Ranking / tie-break (composite desc, trend desc, rs desc, volume desc, momentum desc, breakout desc, symbol asc)
WHY: PROPOSED — REQUIRES HUMAN APPROVAL (B2 spec Section 12, D14) — the specific key order is authored, not sourced.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES for a `sort_key` function signature that takes a scored-row type and returns a comparable tuple, with no fields populated; NO for a hardcoded seven-key comparator.

B2 DEPENDENCY: Watchlist eligibility (K = 10)
WHY: PROPOSED — REQUIRES HUMAN APPROVAL, and explicitly flagged `AUTHORITY: NONE`, `STATUS: UNRESOLVED` (D12) — like the cutoff, zero evidentiary basis.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES for a generic `watchlist_limit: int` configuration field; NO for a hardcoded `TOP_K = 10` constant or a `LIMIT 10` query.

B2 DEPENDENCY: Reason codes (vocabulary and exact numeric triggers)
WHY: PROPOSED — REQUIRES HUMAN APPROVAL (B2 spec Section 14, D16); the vocabulary and every trigger threshold are authored, not sourced.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES for a `reason_codes: list[str]` field type with no fixed vocabulary encoded (e.g., a free-form string list rather than a committed enum); NO for a fixed enum populated with the proposed 16-code vocabulary, and NO for any code evaluating the proposed triggers.

B2 DEPENDENCY: Versioning (`score_version` scheme, approver, bump rules)
WHY: PROPOSED — REQUIRES HUMAN APPROVAL (B2 spec Section 15, D17) — the semver-like scheme and approval process are authored, not sourced.
CAN A NEUTRAL INTERFACE EXIST WITHOUT DECIDING IT: YES — a `score_version: str` field with no format validation baked in is neutral; a regex/constraint enforcing the specific `eqscore-MAJOR.MINOR.PATCH` format would encode a proposal, though a low-consequence one (it does not affect scoring, ranking, or eligibility).

## 5. B3 Dependency Analysis

B3 DEPENDENCY: NIFTY 500 universe (constituent list)
WHY: No NIFTY 500 constituent list exists anywhere in the repository (confirmed in the prior sensitivity study and re-confirmed here: `config/symbols.py` defines only three index instruments).
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — a `Symbol` dataclass/schema (fields: `symbol`, `nse_symbol`, `yfinance_ticker`, `broker_token`, `isin`, `company_name`, `sector`, `active_status`, as named in the original design adjudication) can be defined with no rows populated. A functional universe loader cannot operate without the data.

B3 DEPENDENCY: Constituent history (index-membership changes over time)
WHY: Not present in the repository; not addressed at all by B2 or the freeze-policy row.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES for a schema field (e.g., `effective_from`/`effective_to` on a constituent record); the survivorship-bias question itself remains an unresolved design/B3 issue regardless of schema.

B3 DEPENDENCY: NIFTY 500 benchmark (daily close series)
WHY: Confirmed absent — the only price series in the repository is a 120-session NIFTY 50 index series (per the sensitivity study), not NIFTY 500.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — a benchmark-series interface (`get_benchmark_series(date_range) -> list[Bar]`) can be defined; it cannot be exercised or return real values without the data.

B3 DEPENDENCY: Sector mapping
WHY: No sector taxonomy exists anywhere in the repository (confirmed in the sensitivity study).
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — a `sector: str` field on the `Symbol` schema is neutral as a field; choosing a specific taxonomy (GICS vs. NSE's own classification vs. something else) is a B3-level decision, not resolvable by a field declaration alone.

B3 DEPENDENCY: Daily OHLCV (per-stock)
WHY: Confirmed absent for any NIFTY 500 equity.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — a `Bar(date, open, high, low, close, volume)` dataclass/schema can be defined and is already implicit in the B2 spec's Section 3 input definition; it requires no B3 data to exist as a type.

B3 DEPENDENCY: Volume
WHY: The one available price series in the repository has zero volume on every bar (index-feed convention); no equity volume data exists at all.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — `volume: int | None` as a `Bar` field is neutral; the D04/D19 usability rule that consumes it is a B2 (not B3) dependency, already covered in Section 4.

B3 DEPENDENCY: Corporate-action basis (adjusted vs. unadjusted)
WHY: Not resolved anywhere in governing material; G2 treats corporate-action adjustment as an acceptance gate but does not specify the adjustment method or source.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES for a boolean/enum flag (`adjustment_basis: Literal["adjusted","unadjusted"]`) as a schema field with no value asserted as correct; NO functional acceptance gate can operate without knowing which basis the actual data provider uses.

B3 DEPENDENCY: Trading calendar
WHY: The B2 spec itself flags this as unresolved (D18: "How `expected_asof_date` is derived (holiday-calendar source) is a HUMAN-DECISION not resolvable from the sources"). No NSE holiday-calendar source was found anywhere in the repository.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — a `expected_asof_date: date` field, or a `TradingCalendar` interface with an unimplemented `previous_session(date) -> date` method, can exist; the STALE-detection logic that depends on it (B2 D18/Section 7) cannot function without a real calendar source.

B3 DEPENDENCY: Freshness/staleness metadata
WHY: STALE status logic is specified relative to `asof_date` (B2 Section 7), which itself needs the trading calendar above.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — the `asof_date`/`expected_asof_date` fields and the status enum {VALID, INSUFFICIENT_HISTORY, STALE, FAILED} are already SOURCE-DERIVED (G1/G2) and can be encoded as a type; the comparison logic depends on B3 calendar data to run correctly.

B3 DEPENDENCY: 252+ usable daily bars per stock
WHY: No stock in the repository has any bars at all, let alone 252; the sensitivity study found the one available series has only 120 sessions and is not even equity data.
CAN A DATA CONTRACT / INTERFACE EXIST WITHOUT THE DATA: YES — `w52_complete: bool` is already a SOURCE-DERIVED field name from the governing material and can be typed; it cannot be meaningfully populated without real per-stock history.

## 6. Structural Build Matrix

| Item | Category | B2 Dependency | B3 Dependency | Build Status | Why |
|------|----------|---------------|---------------|--------------|-----|
| 1. Package/module structure (`equity_intel/` directory skeleton, `__init__.py`, subpackage layout) | Structural | None | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Directory/package layout embeds no numeric or universe decision, but creating it is explicitly listed as prohibited under this task's read-only boundary ("Do NOT create equity_intel/"); classified as scaffold-buildable in principle, NOT PERMITTED in this task |
| 2. Data contracts (`Bar`, `Symbol`, scan-result record shapes) | Structural | Low (field names only; already implied by B2 Section 3) | Low (field names only) | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Field shapes can be defined without values; still code, so still prohibited under this task's freeze scope until authorized as a separate implementation task |
| 3. Type definitions (status enum, classification-tag enum with vocabulary only, state enum) | Structural | Low (vocabulary is SOURCE-DERIVED for statuses/tags; trigger logic is not) | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Enum *names* are already governance-approved (G1); populating trigger logic behind them is BLOCKED BY B2 |
| 4. Configuration schemas (e.g., a `candidate_cutoff`, `watchlist_limit`, `score_version` config surface with no default values) | Structural | Medium (must not embed default numbers) | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | A schema with unset/None defaults is neutral; a schema shipping `candidate_cutoff: int = 70` is not (see Section 7) |
| 5. Database schema (tables/columns for scan results, `paper_watchlist`, without seeding candidate-cutoff/K values) | Structural | Medium (column *existence* is neutral; a `DEFAULT 70` constraint would not be) | Medium (schema can exist without data) | BLOCKED BY BOTH (pending release) / scaffold-only in principle | `data/equity_intel.db` creation is explicitly prohibited by this task's read-only boundary regardless of neutrality |
| 6. Repository/data-access interfaces (abstract read/write methods, no concrete data source) | Structural | Low | Low | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | An interface with no implementation locks no data-vendor or threshold choice |
| 7. Scanner orchestration skeleton (empty pipeline stages: load -> feature -> score -> classify -> persist, no logic) | Structural | Low (must not call real scoring) | Low (must not call real data acquisition) | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | An empty pipeline shell with stub stages locks no decision; a pipeline that calls real B2 band logic or real B3 acquisition would not be a shell |
| 8. Pure indicator interfaces (`compute_ema(closes, n) -> float`, `compute_rsi(closes) -> float`, generic math with no B2 band applied) | Structural | None (generic technical-analysis math is not itself a B2 proposal; the *thresholds applied to its output* are) | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | EMA/RSI/ROC formulas are standard, parameterized functions; the B2 spec's *use* of specific periods (20/50/200; 14; 10) to produce a *score* is the proposal, not the existence of a generic indicator function |
| 9. Scoring interfaces (`ScoreComponent` protocol: `compute(bars) -> int | None`, no band table populated) | Structural | Medium — the interface itself is neutral per the task's own example, but any populated band or default behavior on missing input is not | Low | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Matches the task's own "generic `ScoreComponent` interface may be neutral" example precisely |
| 10. Classification interfaces (a function signature `classify(scores) -> ClassificationResult`, no trigger thresholds implemented) | Structural | Medium (vocabulary sourced; trigger logic not) | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Signature is neutral; a working `classify()` body is BLOCKED BY B2 |
| 11. State-machine definitions (enum + allowed-transition graph, no transition conditions implemented) | Structural | Medium (state names PROPOSED; transition thresholds unapproved) | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | A transition-graph *shape* with unimplemented guard conditions is neutral; implemented guards are BLOCKED BY B2 |
| 12. Paper-watchlist persistence interface (abstract `write_watchlist(rows)`, no K, no schema defaults) | Structural | Medium (must not encode K=10) | Low | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Matches the task's own "generic `watchlist_limit` field may be neutral" example |
| 13. Dashboard route/interface skeleton (empty Flask routes returning "not implemented", no candidate data rendered) | Structural | None | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Route registration alone locks no threshold; explicitly prohibited in this task regardless ("Do NOT modify dashboard implementation") |
| 14. Import-boundary enforcement tests (static test asserting `equity_intel/` never imports the forbidden module list) | Structural | None | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Enforces an already-approved constraint (freeze-policy row); requires the package to exist first, so cannot precede item 1; prohibited in this task ("Do NOT create tests") |
| 15. Execution-isolation tests (assert scan raises `RuntimeError` if `execution_mode` is LIVE) | Structural | None | None | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Tests an already-approved safety constraint using the already-existing `core.oms.execution_mode`; prohibited in this task |
| 16. Data-validation framework (generic bad-bar/duplicate-date/non-positive-price checks, no vendor assumed) | Structural | Low | Medium (must not assume a specific vendor's data shape) | BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD | Generic validation logic (the kind already partly exercised in the sensitivity study's illustrative script) is close to neutral if written vendor-agnostically; prohibited in this task regardless |
| 17. Actual market-data acquisition | Decisional/Functional | None directly | HIGH — requires selecting a vendor/source | BLOCKED BY B3 | No approved NIFTY 500 data source exists; acquiring data would itself select a vendor, a B3 decision |
| 18. Actual NIFTY 500 universe loading | Decisional/Functional | None directly | HIGH — is the B3 decision itself | BLOCKED BY B3 | Loading any concrete universe list selects a source/vendor/version, the core unresolved B3 question |
| 19. Actual scoring implementation (real EMA/RSI/band logic producing real point values) | Decisional/Functional | HIGH | Depends on data existing | BLOCKED BY B2 (and by B3 for any real input) | Implementing the proposed bands is choosing them; not neutral under the task's own test |
| 20. Candidate selection (applying composite >= 70) | Decisional/Functional | HIGH (unapproved, unresolved D11) | Depends on scoring existing | BLOCKED BY B2 | D11 has zero evidentiary basis; implementing it selects an unapproved number |
| 21. Watchlist generation (applying top-10) | Decisional/Functional | HIGH (unapproved, unresolved D12) | Depends on candidates existing | BLOCKED BY B2 | D12 has zero evidentiary basis; same reasoning as item 20 |
| 22. Dashboard candidate display (rendering real scored/ranked rows) | Decisional/Functional | HIGH (depends on scoring/ranking) | HIGH (depends on real data) | BLOCKED BY BOTH | Cannot display candidates that cannot legitimately exist yet; also explicitly prohibited under this task's freeze regardless of B2/B3 state ("Do NOT modify dashboard implementation") |
| 23. Scheduler integration | Decisional/Functional (architecturally not even required yet) | None directly | Depends on a working scanner existing | NOT PERMITTED UNDER CURRENT FREEZE | Design material states no scheduler is required for the initial architecture; nothing to integrate yet, and scheduler work is not part of the approved B1 exception scope at all |

## 7. "Would This Lock a Decision?" Analysis

- A generic `ScoreComponent` interface (`compute(bars) -> int | None`) with no band table populated: NEUTRAL — does not lock B2.
- A database column named literally `candidate_cutoff_70`, or any column whose *name* encodes the value: NOT NEUTRAL — locks D11 by naming.
- A generic `watchlist_limit: int` configuration field with no default: NEUTRAL — does not lock D12.
- A hardcoded `TOP_K = 10` constant anywhere in code: NOT NEUTRAL — locks D12.
- A generic `score: int | None` field/type on a scored-row record: NEUTRAL — does not lock any component's band table.
- Implementing the actual 0-20 scoring bands (RSI/ROC/rp60/RVOL/dist52 tables) in code: NOT NEUTRAL — this is precisely what D01-D05 leave open; implementing it selects the proposed values by making them the only values the code can produce.
- A classification enum containing only the vocabulary names (STRONG_TREND, WEAK_TREND, MOMENTUM, RELATIVE_STRENGTH, VOLUME_EXPANSION, BREAKOUT_WATCH, NEUTRAL, DATA_INVALID) with no trigger logic attached: NEUTRAL for the *names* (SOURCE-DERIVED, G1), but the moment any code decides *when* to assign a tag from a component score, that logic is NOT NEUTRAL (locks D10's thresholds).
- A `composite: int | None` field with an aggregation function that must choose behavior on a missing component: NOT NEUTRAL the moment the function body exists (Section 4's None-propagation finding) — the type alone (`Optional[int]`) is neutral, but any implemented aggregator is not.
- A `score_version: str` field with no format validation: NEUTRAL. A validator enforcing the exact `eqscore-MAJOR.MINOR.PATCH` pattern: mildly NOT NEUTRAL (locks D17's naming scheme, though this is the lowest-consequence lock in the model since it affects no score or ranking).
- An empty scanner orchestration pipeline whose stages are stub functions raising `NotImplementedError`: NEUTRAL — locks no decision, as long as no stage's stub return type or default behavior implies a specific band, cutoff, or vendor.
- A `Symbol` dataclass with fields named per the original design proposal (`symbol`, `nse_symbol`, `yfinance_ticker`, `broker_token`, `isin`, `company_name`, `sector`, `active_status`) but zero rows populated: mostly NEUTRAL, though the field *name* `yfinance_ticker` mildly presumes yfinance as a data source in the schema itself — this is flagged in Section 8 as a soft, low-consequence lock worth flagging even though it is only a field name and not a live import or configured vendor call.

## 8. "Would This Lock a B3 Data Assumption?" Analysis

| Assumption | Would a neutral schema/interface silently choose it? | Finding |
|---|---|---|
| NIFTY 500 source (index provider) | No, if the `Symbol`/universe-loader interface takes a source as a parameter rather than hardcoding one | Neutral if written generically |
| Vendor (Upstox vs. yfinance vs. other) | Partially — a field literally named `yfinance_ticker` (as proposed in the original design-adjudication material) presumes yfinance is in scope as *a* candidate vendor, even though B2/G2 make Upstox primary and yfinance secondary-if-enabled. This is a soft assumption baked into a field *name*, not a live choice, but it is worth flagging rather than silently accepting | Soft lock — flagged, not fatal, should be named more generically (e.g., `secondary_vendor_ticker`) if built |
| Symbol format (exchange-qualified vs. bare ticker) | No, if the field is typed as an opaque string with documented meaning rather than validated against a specific exchange's format | Neutral if written generically |
| Sector taxonomy (GICS vs. NSE's own) | No, if `sector: str` is an untyped/free-text field rather than a constrained enum of a specific taxonomy's values | Neutral only if left as free text; an enum of GICS codes would lock a taxonomy choice |
| Adjusted vs. unadjusted prices | Partially — G2 requires corporate-action adjustment as an acceptance gate, but does not say which method/source performs the adjustment. A schema field flagging adjustment basis is neutral; a *validator* that assumes a specific adjustment convention (e.g., assumes splits-only, no dividends) would not be | Neutral if the field only records basis, not if logic assumes a specific method |
| Trading-calendar provider (NSE holiday API vs. hardcoded list vs. a vendor's own calendar) | No, if `TradingCalendar` is an interface with no implementation | Neutral if no concrete implementation is written |
| Volume semantics (does zero mean no trades or missing data?) | This is actually a B2 concern already resolved in the spec (D19: zero and missing are distinct; missing is never converted to zero) — a schema using `volume: int | None` (not defaulting to `0`) is consistent with that and does not add a new B3 assumption | Neutral, and required to stay faithful to B2's own I6 invariant |
| Benchmark source (which index feed serves NIFTY 500 daily closes) | No, if the benchmark-series interface takes a source identifier as a parameter rather than hardcoding a fetch call to one provider | Neutral if written generically |

**Overall finding:** most B3-adjacent structural elements can be written without silently choosing a vendor, taxonomy, or format, provided field names are kept generic (the one soft exception being a `yfinance_ticker`-style field name inherited from the original, non-authoritative design proposal — worth renaming if this scaffold is ever built).

## 9. Freeze Compatibility

Every item classified as "BUILDABLE ONLY AS NON-FUNCTIONAL SCAFFOLD" in Section 6 is evaluated here on the two separate axes the task requires. "Technically buildable" reflects only whether the artifact can be written without embedding an unapproved B2/B3 decision (Sections 4, 5, 7, 8). "Governance-permitted" reflects whether *this specific task* is authorized to create it, and separately whether a *future, properly scoped implementation task* would be.

| Item | Technically Buildable | Governance-Permitted (this task) | Governance-Permitted (a future implementation task, in principle) |
|---|---|---|---|
| 1. Package/module structure | YES | NO — this task's explicit boundary forbids creating `equity_intel/` | YES, under the existing B1 exception's approved scope, once separately authorized |
| 2. Data contracts | YES | NO — this task creates no code | YES, same basis |
| 3. Type definitions | YES (vocabulary only) | NO | YES, same basis |
| 4. Configuration schemas | YES (no defaults) | NO | YES, same basis |
| 5. Database schema | YES (structure only, no seeded 70/10) | NO — this task forbids `data/equity_intel.db` outright | YES, same basis, but the B1 exception's own "guard refusing OMS DBs" constraint must be implemented alongside the schema, not after |
| 6. Repository/data-access interfaces | YES | NO | YES |
| 7. Scanner orchestration skeleton | YES (stub stages only) | NO — this task forbids `scripts/equity_scan.py` | YES, same basis |
| 8. Pure indicator interfaces | YES | NO | YES |
| 9. Scoring interfaces | YES | NO | YES |
| 10. Classification interfaces | YES (signature only) | NO | YES |
| 11. State-machine definitions | YES (shape only) | NO | YES |
| 12. Paper-watchlist persistence interface | YES (no K) | NO | YES |
| 13. Dashboard route/interface skeleton | YES (empty routes) | NO — this task forbids modifying the dashboard | YES, same basis, additive only per the freeze-policy row |
| 14. Import-boundary enforcement tests | YES (once package exists) | NO — this task forbids creating tests | YES, same basis |
| 15. Execution-isolation tests | YES | NO | YES |
| 16. Data-validation framework | YES (vendor-agnostic) | NO | YES |

**Finding:** for this specific audit task, GOVERNANCE-PERMITTED is NO for every one of the sixteen structural items, regardless of their technical neutrality, because this task's own read-only boundary explicitly prohibits creating any of them. Technical buildability (Section 6/7/8) and this task's permission to act on it are two different questions with two different answers.

## 10. Minimum Safe Structural Foundation

Described only; not built.

The smallest structural foundation that could theoretically be authorized by a *future, separately-scoped implementation task* (not this one) — without approving B2, releasing B3, selecting a market-data vendor, selecting the NIFTY 500 universe source, implementing candidate scoring, generating watchlists, or touching the options engine — would consist of:

1. The `equity_intel/` package skeleton (empty `__init__.py`, subpackage stubs for `features/`, `scoring/`, `persistence/`, `classification/`) with no logic in any file.
2. Data-contract dataclasses/schemas for `Bar`, `Symbol` (generic field names, no vendor-specific naming), and a `ScanResult` shell record with `Optional` fields for every score and status, defaulting to unset rather than any value.
3. Enum types for the already-SOURCE-DERIVED vocabulary only: the four data statuses (VALID/INSUFFICIENT_HISTORY/STALE/FAILED), the classification tag names (with no trigger logic attached), and the state names (SCORED/ELIGIBLE/CANDIDATE/WATCHLISTED, with no transition conditions attached).
4. Abstract repository/data-access interfaces (`MarketDataSource`, `WatchlistRepository`, `TradingCalendar`) with no concrete implementation and no vendor selected.
5. A no-op orchestration shell (`scripts/equity_scan.py` containing stage stubs that raise `NotImplementedError`), sufficient to prove the process boundary (separate from `main.py`/`continuous_engine.py`) without ever computing or persisting a real value.
6. Import-boundary and execution-isolation tests, written against the empty skeleton, to lock in the already-approved constraints (forbidden-import list, `RuntimeError` on LIVE mode) as soon as *any* code exists in the package — these are the one category of "test" that is itself structural, since it enforces an already-approved constraint rather than a proposed one.
7. A `data/equity_intel.db` schema (DDL only) with the guard against OMS databases, and table columns for cutoff/K/versioning left as nullable/parameterized rather than seeded with 70, 10, or any specific `score_version`.

This foundation, if built, would leave every single B2 numeric decision and every B3 data question exactly as open as they are today — nothing in it could run end-to-end, produce a score, a candidate, a watchlist row, or a dashboard number, because every path that would require an unapproved number or an unavailable data source is a stub. This task does not authorize building it; Section 9 already establishes that governance permission for *this task* to create any of it is NO.

## 11. Explicitly Blocked Work

- All twenty-three items in Section 6 that are not scaffold-only (items 17-23: actual data acquisition, universe loading, scoring implementation, candidate selection, watchlist generation, dashboard candidate display, scheduler integration) are BLOCKED BY B2, BLOCKED BY B3, BLOCKED BY BOTH, or NOT PERMITTED UNDER CURRENT FREEZE, per Section 6's table.
- All sixteen scaffold-eligible items (1-16) are additionally NOT PERMITTED to be created *by this task*, per Section 9, independent of their technical neutrality.
- Any modification to `main.py`, `continuous_engine.py`, `paper_engine.py`, any OMS file, risk management, broker code, strategies, `config/symbols.py`, the dashboard implementation, or the React frontend — forbidden by this task's explicit boundary and, for most of these, by the freeze-policy row's own "NO MODIFICATION to" list.
- Any acquisition or import of production market data, any scoring implementation, any candidate generation, any watchlist generation, any scheduler integration — all forbidden by this task's explicit boundary, independent of the B2/B3 analysis above.
- Modifying the B2 specification or B3 governance state — forbidden by this task's boundary; also, this task has no authority to alter either regardless.

## 12. Human Decisions Still Required

Unchanged by this audit, and not newly resolved by it:
- All B2 decisions D01-D19 (component bands, composite missing-component rule, classification triggers, candidate cutoff, watchlist K, ranking tie-break, reason codes, versioning scheme, trading-calendar source, volume-usability count) as enumerated in `B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md` Section 18.
- The B3 NIFTY 500 universe source, vendor, benchmark series, sector taxonomy, and corporate-action adjustment method — none of which this audit selects or recommends.
- Whether and when a separately-scoped implementation task will be authorized to build the minimum safe structural foundation described in Section 10 (this audit does not request or grant that authorization).
- The soft field-naming concern flagged in Section 8 (`yfinance_ticker`-style naming inherited from the non-authoritative design proposal) — a minor point for whoever eventually authors the actual `Symbol` schema to reconsider, not a governance blocker.

## 13. Final Boundary Decision

STRUCTURAL WORK MAY PROCEED ONLY AS NON-FUNCTIONAL SCAFFOLD

This reflects two independent findings that must both be read together: (1) on pure technical/decisional-neutrality grounds (Sections 6-8), sixteen of the twenty-three items are scaffold-buildable without locking any unapproved B2 number or B3 assumption, provided they are written generically (no seeded cutoff/K values, no vendor-specific field names, no populated band tables); and (2) under this specific task's own read-only boundary (Section 9), none of that scaffold may be created *by this task* — the boundary decision therefore describes what a future, separately-authorized implementation task could build as scaffold, not what happens next automatically. No implementation, of scaffold or otherwise, occurs as a result of this audit.

## 13a. Traceability Correction (Phase 1, appended 2026-09-22)

**Defect identified:** the Final Chat Report accompanying this audit stated "B2-BLOCKED: 7 items" without enumerating them, and its neutral-language summary named only 4 of the 7 (items 19, 20, 21, 22) as examples. That summary line was an imprecise shorthand for "the 7 items outside the 16-item technically-buildable scaffold set," not a claim that all 7 are blocked by B2 specifically. This section corrects that traceability gap by enumerating all 7 items with their actual dependency as already recorded in Section 6's matrix. **No substantive boundary conclusion changes.** The count 16 technically-buildable + 7 blocked = 23 total was already arithmetically correct (Section 6 lists exactly 23 items; Section 9's freeze-compatibility table lists exactly items 1-16 as the technically-buildable set); only the explicit enumeration of the complementary 7 was missing.

### B2-BLOCKED ITEMS — EXPLICIT ENUMERATION
----------------------------------------

1. Item 17 — Actual market-data acquisition
   B2 dependency: None directly
   Reason: BLOCKED BY B3, not B2. No approved NIFTY 500 data source exists; acquiring data would itself select a vendor, a B3 decision (Section 6, row 17). Included in the 7-item complement of the scaffold set because it is decisional/functional work, not because B2 blocks it.

2. Item 18 — Actual NIFTY 500 universe loading
   B2 dependency: None directly
   Reason: BLOCKED BY B3, not B2. Loading any concrete universe list selects a source/vendor/version, the core unresolved B3 question (Section 6, row 18). Same basis as item 17 for inclusion in the 7-item set.

3. Item 19 — Actual scoring implementation (real EMA/RSI/band logic producing real point values)
   B2 dependency: HIGH — implements the proposed D01-D05 bands directly
   Reason: BLOCKED BY B2 (and by B3 for any real input). Implementing the proposed bands is choosing them, which is not neutral under the audit's own "would this lock a decision" test (Section 6, row 19; Section 7).

4. Item 20 — Candidate selection (applying composite >= 70)
   B2 dependency: HIGH — implements the unapproved, evidence-free D11 cutoff
   Reason: BLOCKED BY B2. D11 has zero evidentiary basis in the B2 specification's own decision register; implementing it selects an unapproved number (Section 6, row 20).

5. Item 21 — Watchlist generation (applying top-10)
   B2 dependency: HIGH — implements the unapproved, evidence-free D12 watchlist size
   Reason: BLOCKED BY B2. D12 has zero evidentiary basis, identical reasoning to item 20 (Section 6, row 21).

6. Item 22 — Dashboard candidate display (rendering real scored/ranked rows)
   B2 dependency: HIGH — depends on scoring and ranking that are themselves B2-blocked
   Reason: BLOCKED BY BOTH B2 and B3. Cannot display candidates that cannot legitimately exist yet under either governance gate; also independently prohibited by this task's own freeze boundary regardless of B2/B3 state (Section 6, row 22).

7. Item 23 — Scheduler integration
   B2 dependency: None
   Reason: NOT PERMITTED UNDER CURRENT FREEZE — not a B2 or B3 dependency at all. The design material states no scheduler is required for the initial architecture, and scheduler work was never part of the approved B1 exception scope (Section 6, row 23). Included in the 7-item complement solely because it is decisional/functional work outside the 16-item scaffold set, not because either B2 or B3 blocks it.

**Corrected characterization:** of the 7 items outside the technically-buildable scaffold set, 2 are BLOCKED BY B3 only (17, 18), 3 are BLOCKED BY B2 only (19, 20, 21), 1 is BLOCKED BY BOTH (22), and 1 is NOT PERMITTED UNDER CURRENT FREEZE independent of B2/B3 (23). The original "B2-BLOCKED: 7 items" label in the Final Chat Report should be read as "outside the scaffold-buildable set: 7 items," not "blocked by B2 specifically: 7 items." This correction changes no build-status classification in Section 6 and no conclusion in Section 13.

**Verification:** 16 (Section 9's enumerated technically-buildable items 1-16) + 7 (items 17-23 enumerated above) = 23 (the full matrix in Section 6). The matrix is internally traceable.

## 14. Repository Safety

Implementation Started: NO
B2 Released: NO
B3 Released: NO
Unrelated Files Modified: 0
Files Staged: 0

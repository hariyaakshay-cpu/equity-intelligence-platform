# B3 DATA & SOURCE READINESS AUDIT — 2026-09-22

Status: READ-ONLY / GOVERNANCE AUDIT. No implementation performed.

## 1. Preflight

Repository root: /sessions/rcw-01hchdf6wijvz9efphgzw1sj/mnt/algo_trader
Branch: main
HEAD: 03ccce95ff47af479d9382723ae91694d39fb6a2 (matches required baseline)
Pre-existing modified/staged/untracked at Phase 0: 267 status lines total; 0 staged; 130 untracked. Working tree left untouched; no cleanup attempted (bytecode cleanup failure from the prior task is explicitly out of scope for this audit and was not retried or investigated).

## 2. Governing Sources

| Source | Status | Location |
|---|---|---|
| B2/B3 Structural Build Boundary Audit | FOUND | research/b2_b3_structural_build_boundary_audit_2026-09-22.md (repository) |
| B2 Authoritative Scoring Specification | FOUND | session output area (B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md; not a repository file — B2 is deliberately kept outside the repo until released) |
| B2 Scoring-Threshold Adjudication | FOUND | session output area (B2_SCORING_THRESHOLD_ADJUDICATION_2026-09-21.md) |
| Development freeze policy | FOUND | docs/development_freeze_policy.md (repository) |
| B1 governance exception | FOUND | commit 03ccce95ff47af479d9382723ae91694d39fb6a2 = HEAD, matches the freeze-policy row |
| Equity Intelligence design/architecture material | FOUND | session output area (EQUITY_INTELLIGENCE_DESIGN_ADJUDICATION_2026-09-21.md; explicitly proposals only, non-authoritative) |
| Equity Intelligence neutral scaffold | FOUND | equity_intel/ (repository) |
| B3 threshold-sensitivity study | FOUND | research/b2_threshold_sensitivity_study_2026-09-22.md (repository) — established the data-availability baseline this audit extends |
| A dedicated B3 specification/adjudication document (analogous to the B2 spec) | MISSING | No file of this kind exists anywhere searched (repository or session output area). B3 has never been the subject of its own authoring task; everything known about B3 comes from the B1 freeze-policy row's constraints, the B2 documents' passing references to B3, and the two prior research audits. |
| NIFTY 500 constituent list/file | MISSING | Not found anywhere in the repository (see Section 4) |
| Sector mapping file | MISSING | Not found anywhere in the repository (see Section 7) |
| Benchmark (NIFTY 500 index) historical data file | MISSING | Not found anywhere in the repository (see Section 6) |
| Instrument-master / bulk NSE dump (e.g. an "NSE.json.gz"-style file) | MISSING | Not found in the repository. `core/upstox_data.py` reads a per-symbol `upstox_instrument_key` from config/symbols.py's 12 hand-maintained entries; there is no bulk instrument-master ingestion capability, cached file, or reference to one, anywhere in the codebase that was located |

No source was substituted, inferred from memory, or assumed present without being located this session.

## 3. Source Availability

All repository paths above were opened and read directly in this session (not recalled from prior-turn memory). The session-output-area documents were re-confirmed present by reading their first line each. No document was treated as authoritative without being reopened.

One correction to a claim made in an earlier B2/B3 structural audit this session: that audit stated `config/symbols.py` "defines exactly three index instruments (NIFTY, BANKNIFTY, SENSEX)." Re-reading the full file (200 lines, not the first 80) this session shows that claim was **incomplete, not wrong about the conclusion**: the file actually defines **12 instruments** — 4 indices (NIFTY, BANKNIFTY, SENSEX, NIFTYIT) and 8 individual F&O-underlying stocks (RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, WIPRO, BAJFINANCE, TATASTEEL), each carrying options-contract routing metadata (`lot_size`, `tick_size`, `margin`, `category`, and for some, `upstox_instrument_key`) and no `sector`, `isin`, or NIFTY-500-membership field of any kind. This is disclosed here because the underlying conclusion — this file is not, and must not become, a NIFTY 500 universe source — is unaffected and in fact reinforced (12 hand-picked options underlyings is further from a 500-constituent equity universe than "3 indices" suggested), but the earlier document's specific instrument count was inaccurate and should be read as corrected by this section rather than silently left standing.

## 4. NIFTY 500 Universe Readiness

1. Constituent list: not present anywhere in the repository.
2. Constituent symbols: none exist to audit.
3. Symbol format: undefined — no source to define it against.
4. Exchange identity: undefined.
5. Effective/as-of date: not applicable — no list exists to date.
6. Constituent revision handling: not defined anywhere in governing material (B2 spec Section 3 lists `InstrumentMember` field concepts only, and B3 Dependency Analysis in the structural audit records "constituent history" as absent and its survivorship question as unresolved).
7. Historical constituent requirements: not resolved — the structural audit flagged survivorship bias as an open B3 question with no source.
8. Reproducibility: not assessable — nothing to reproduce.
9. Source authority: none. No governing document names a vendor, an index-provider feed, or a manual list as authoritative for NIFTY 500 membership.
10. Present and usable: NO.

Explicit answers:
- Is there an authoritative NIFTY 500 constituent source? **No.**
- Is its as-of/effective date defined? **No — moot, since no source exists.**
- Is the universe reproducible? **No.**
- Is the source approved by B3 governance? **No — B3 governance has not approved any source because B3 itself is BLOCKED and no B3-specific decision document exists (Section 2).**
- Is implementation possible without inventing a universe? **No.** Any scan would require either fabricating a constituent list (explicitly forbidden by this task and by the original design-adjudication material's "no fabricated tokens/ISINs/constituents" rule) or halting before the first pipeline stage — which is exactly what the implemented scanner shell (`equity_intel/scanner/shell.py`) does: `_load_universe()` raises `NotImplementedError("B3 NIFTY 500 universe source is BLOCKED (not yet selected)")`.

**This is recorded as a concrete B3 blocker (B3-01).**

## 5. Symbol / Instrument Mapping

No mapping authority exists because there is no universe to map (Section 4). Specifically:
- Exchange symbol format: undefined.
- Vendor symbol (e.g. a yfinance-style `.NS` suffix, seen in config/symbols.py's `RELIANCE.NS` for the unrelated options-underlying list): a convention exists in that unrelated file, but no governing document authorizes reusing it for a NIFTY 500 equity feed, and the freeze policy forbids `config/symbols.py` from becoming that authority.
- Ticker normalization rules: undefined.
- Renamed-security handling: undefined.
- Special characters: undefined.
- Delisted-security handling: undefined.
- Duplicate-identifier handling: undefined.
- Corporate-action identity continuity (e.g. a symbol surviving a merger/spinoff): undefined; only "corporate-action adjustment" of price series is mentioned in G2 as an acceptance gate, which is a price-series concern, not an identity-continuity concern.

**Recorded as a concrete B3 blocker (B3-02).**

## 6. Benchmark Readiness

The B2 specification (Section 4.3, decision D03) names NIFTY 500 as the proposed Relative Strength benchmark, explicitly tagged `HUMAN-DECISION`, `AUTHORITY: HUMAN-DECISION`, not authoritative.

- Benchmark instrument: proposed (NIFTY 500 index) but not approved.
- Benchmark symbol: undefined.
- Benchmark source: undefined — no vendor or feed named.
- Benchmark history: not present. The only index-level historical series in the repository is `data/historical/NIFTY_15minute.csv` (and its 1-minute/5-minute siblings) for the **NIFTY 50** index, not NIFTY 500, confirmed absent by direct search and previously confirmed in `research/b2_threshold_sensitivity_study_2026-09-22.md` Section 4.
- Benchmark effective/as-of date: not applicable — no series exists.
- Required historical length: the B2 spec requires 61 benchmark bars minimum for the relative-strength window (Section 4.3); the only available index series has 120 resampled daily sessions, which would numerically suffice in bar count if it were the right index, but it is the wrong index (NIFTY 50, not NIFTY 500) and its use as a NIFTY 500 substitute is not authorized by any source.
- Adjustment basis: undefined for any benchmark candidate.
- Missing-data behavior: SOURCE-DERIVED at the rule level only (B2 spec: benchmark unavailable/short ⇒ scan ABORTED, not a neutral or zero RS) — this rule is written but has never been exercised against a real benchmark feed because none exists.

Since B2 requires a benchmark that B3 has not authorized or sourced, **this dependency is recorded as a concrete B3 blocker (B3-03)**, distinct from the universe blocker: even if a NIFTY 500 constituent list existed, relative-strength scoring would still have no benchmark series to compare against.

## 7. Sector / Classification Readiness

The original (non-authoritative) design-adjudication material lists `sector` as a required field of the intended universe record, and B2's classification/context material (Section 13) references a `sector` context feature with a note that GICS vs. NSE's own taxonomy is unresolved. `equity_intel/contracts/market_data.py`'s `InstrumentMember.sector` is deliberately typed as `Optional[str]` free text, with no taxonomy enum, precisely because no taxonomy source exists.

- Sector source: none.
- Classification taxonomy: unresolved — neither GICS nor an NSE-native taxonomy is selected, and no third option is named either.
- Sector effective date: not applicable.
- Symbol-to-sector mapping: not present; cannot exist without a universe (Section 4) and a taxonomy.
- Handling of sector changes: undefined.
- Missing-sector behavior: SOURCE-DERIVED only at the general level (I6: missing is never defaulted, applies to sector as to any field) — no sector-specific rule beyond that general invariant exists.
- Reproducibility: not assessable.

Sector context is required by the governing Equity Intelligence design (as a context feature, not a scoring input — B2 invariant I5 keeps it display/context-only), but no authoritative source exists. **Recorded as a concrete B3 blocker (B3-04).**

## 8. Historical Price Data Readiness

Cross-checked against B2 spec Section 3 ("Persisted inputs consumed") and Sections 4.1-4.5:

- OHLC fields required: high, low, close (B2 explicitly states `open` is never used by any component — Section 3). The repository's only relevant series (`data/historical/NIFTY_15minute.csv` etc.) does carry high/low/close/volume columns, so the *shape* is compatible, but the series is index-level (NIFTY 50), not equity data, and covers only 120 resampled daily sessions (confirmed in the prior sensitivity study).
- Adjusted vs. unadjusted basis: undefined for any equity source (G2 requires adjustment as an acceptance gate but names no method or vendor — carried forward as PROPOSED in the B2 spec, invariant I8).
- Corporate-action treatment: undefined beyond the acceptance-gate statement above.
- Trading-calendar basis: undefined — B2 spec's own decision register (D18) flags "how `expected_asof_date` is derived (holiday-calendar source)" as a HUMAN-DECISION not resolvable from any source found.
- Minimum history: PROPOSED only (252 bars for VALID status / Structure component, B2 Section 4.5-4.6) — not authoritative since B2 is not released, and in any case unmet by any data in the repository (max 120 sessions available, and that for the wrong instrument).
- Expected bar frequency: daily, per B2 Section 3 — consistent with the shape of the one series available, but that series is not an equity series.
- Timestamp/date semantics: the available CSV uses a `timestamp` column at 15-minute granularity, which the earlier sensitivity study resampled to daily closes; no equity source with native daily bars was found to check its own date semantics against.
- Missing-session / duplicate-bar / stale-data / invalid-price handling: rules are SOURCE-DERIVED at the general invariant level (I6, I7) and PROPOSED at the specific-threshold level (STALE definition, D18); no equity data exists to exercise any of these rules against.
- Data quality validation: `equity_intel/validation/framework.py` implements generic, vendor-agnostic checks (duplicate dates, non-positive price, inverted high/low, configurable minimum-history and volume-usability checks) as pure functions with no hardcoded thresholds — this is a technically-ready *mechanism*, but it has no B3-approved data to validate and no B3-approved threshold values to configure it with.
- Source/vendor authority: see Section 12.

No historical daily equity price data exists in the repository for any NIFTY 500 constituent. **Recorded as a concrete B3 blocker (B3-05).**

## 9. Volume Data Readiness

The repository's one available price series (`data/historical/NIFTY_15minute.csv`, and its 1-minute/5-minute siblings) carries a `volume` column, but every value in it is `0` across all 3,001 rows (re-confirmed this session's predecessor task by scanning the full column) — an index-feed convention, not evidence that equity volume is available. **Index volume data does not establish equity volume availability**, and this audit does not treat it as doing so.

- Required volume field: SOURCE-DERIVED as a concept (B2 Section 4.4 requires a `volume` series); PROPOSED for the exact usability rule (D19: ≥15 of the prior 20 bars with volume > 0).
- Minimum usable observations: PROPOSED only (the "15 of 20" figure), not authoritative.
- Zero-volume treatment: SOURCE-DERIVED as a general invariant (never silently zero-filled) plus a PROPOSED specific rule (a real, observed zero on a non-missing bar scores 0 via the RVOL formula, distinct from "missing").
- Missing-volume treatment: SOURCE-DERIVED (I6) — never defaulted to zero.
- Stale-volume treatment: not separately defined from general staleness rules (Section 8).
- Adjusted/unadjusted handling: not applicable to volume in any source found.
- Source authority: none — no equity volume vendor is named.

No equity volume data of any kind exists in the repository. **Recorded as a concrete B3 blocker (B3-06)**, distinct from B3-05 because a source could in principle supply prices without adequate volume (a common real-world vendor limitation), so this is tracked separately per the audit's instruction not to combine unrelated blockers.

## 10. Structure / 52-Week Data Readiness

B2 Section 4.5 requires a 252-bar window (including the current bar) for the Structure/Breakout component and for `w52_complete`.

- Required number of sessions: PROPOSED at 252 (not authoritative — B2 not released).
- Trading-calendar definition: undefined (same D18 gap as Section 8).
- Current-session inclusion: SOURCE-DERIVED as a specific written rule in the B2 spec (252-bar window explicitly includes the current bar, distinct from the 20D/50D windows which exclude it) — a decided rule, but PROPOSED/unauthoritative pending B2 sign-off.
- History completeness: cannot be assessed for any equity — no equity history exists at all (Section 8).
- Missing-bar behavior: covered by the general data-quality rules (Section 11), no structure-specific exception found.
- Corporate-action basis: same undefined gap as Section 8.
- Reproducibility of the 52-week high: not assessable without real data; the *formula* (`max(high)` over the trailing 252-bar window) is deterministic and was independently verified as look-ahead-free in the prior sensitivity study's audit (Section 16 of that report), but a deterministic formula over data that does not exist supplies no readiness.

B3 cannot currently supply 252 sessions of history for any equity candidate — the only real series in the repository (NIFTY 50 index, 120 sessions) is both the wrong instrument type and short by 132 sessions of the proposed (unauthoritative) minimum. **This is the same root blocker as B3-05 (no equity history) expressed at the specific 252-bar requirement; it is not double-counted as a separate blocker ID, and is cross-referenced from the blocker register.**

## 11. Data Quality / Status Readiness

The four-value status vocabulary (VALID, INSUFFICIENT_HISTORY, STALE, FAILED) is SOURCE-DERIVED (G1/G2) and structurally represented in the scaffold (`equity_intel/contracts/quality.py`'s `DataStatus` enum). Whether B3 can support *assigning* these deterministically depends on inputs B3 has not yet supplied:

- Missing data / NaN: general rule is SOURCE-DERIVED (I6, never zero-filled); assignable once real data exists.
- Duplicate bars: the validation framework has a pure, deterministic check (`has_duplicate_dates`) ready to apply to real data; not yet exercised because no real equity data exists.
- Non-trading days: depends on the undefined trading-calendar source (D18).
- Stale observations: the STALE rule itself is PROPOSED, not authoritative, and depends on the same undefined calendar (`is_stale` in the validation framework returns `None` — "undecided" — whenever no `expected_asof_date` is supplied, by design).
- Partial history: INSUFFICIENT_HISTORY is assignable in principle (bar-count check is calendar-independent) but has never been exercised against real equity data.
- Source failure / symbol-not-found: no vendor exists yet to fail against (Section 12).
- Corporate-action anomalies: undefined basis (Section 8).

No new status vocabulary is proposed or required by this audit; the existing four-value vocabulary is retained as governing. The blocking factor here is not the vocabulary but the absence of a trading-calendar source (D18) and of any real data to classify — both already captured as B3-03/B3-05 dependencies and the calendar gap specifically as B3-07 below.

**Recorded as a concrete B3 blocker (B3-07): trading-calendar source undefined**, needed for STALE detection and structural completeness assessment across Sections 8, 9, and 10.

## 12. Vendor / Source Authority

- Primary source: G2 (decision-freeze material) names Upstox as primary for daily candles "if explicitly enabled and tagged," but no B3-specific document formally authorizes Upstox as the NIFTY 500 equity data source — this is a G2-level design preference carried into B2, not a B3 sign-off.
- Secondary source: yfinance is named in G2 as usable "only if explicitly enabled and tagged"; `yfinance==1.5.1` is present in `requirements.txt` (confirmed this session), meaning the *library* is already an installed dependency, but its use for NIFTY 500 equities specifically has not been authorized by any B3 decision — dependency presence is not source authorization.
- Fallback rules: none defined between Upstox and yfinance beyond the general "secondary only if explicitly enabled and tagged" language; no precedence order, no criteria for when to fall back, is specified.
- Credentials/dependency assumptions: `core/upstox_data.py` reads a token from a local cache (`TOKEN_CACHE_PATH`) via `core/upstox_data.py` (not `core/historical_data.py`, which remains forbidden per the freeze-policy import-boundary list) — this token infrastructure exists and is usable in principle for the *options* system's per-symbol routing, but nothing in it or in any governing document extends its authority to a bulk NIFTY 500 fetch.
- API/library already present: yfinance (pip), and Upstox access via `core/upstox_data.py`'s existing token/session handling — both exist as *capabilities*, not as B3-authorized *sources*.
- Rate limits: not documented for either candidate anywhere found (consistent with the earlier B2 audit's finding that "adjustment basis and rate limits NOT stated in docs" for Upstox).
- Reproducibility: not assessable without a selected, versioned source.
- Historical-data availability: unverified for NIFTY 500 breadth from either candidate — no attempt was made to query either vendor (forbidden by this task), so this is recorded as unverified, not as confirmed-available.
- Corporate-action basis: undefined for either candidate.

**SOURCE AUTHORITY UNRESOLVED.** Neither Upstox nor yfinance has been designated authoritative for NIFTY 500 equity/benchmark/sector data by any B3-level decision; both remain, at most, G2-level design preferences for future consideration. **Recorded as a concrete B3 blocker (B3-08).**

## 13. Persistence Readiness

The implemented neutral scaffold (`equity_intel/persistence/schema.py`, `equity_intel/persistence/repositories.py`) was inspected without modification:

- Equity universe persistence: an `instruments` table exists in the DDL (symbol, exchange_symbol, secondary_vendor_ticker, instrument_key, isin, company_name, sector, active) — shape-ready, empty, no vendor/taxonomy assumed.
- Market-data persistence: a `market_observations` table exists (instrument_id, observation_date, high, low, close, volume) — shape-ready.
- Feature input persistence: a `feature_sets` table exists, matching the FeatureSet contract's field names — shape-ready.
- Source/as-of metadata: `scan_runs` carries `asof_date`, `expected_asof_date`, `score_version`, `status` — shape-ready, no values populated.
- Scan timestamp: covered by `scan_runs.asof_date`.
- Data-quality status: `data_quality_results` table exists (status, reason, n_bars, w52_complete) — shape-ready.
- Reproducibility / versioning: `score_version` is a schema column with no format enforced beyond being text; no versioning process has been exercised because no scan has run.
- `UniverseRepository`, `MarketDataRepository` (with a `get_benchmark_observations` method), `FeatureRepository`, `ScoreRepository`, `CandidateRepository`, `WatchlistRepository`: all present as abstract interfaces in `equity_intel/persistence/repositories.py`, every concrete method raising `NotImplementedError` naming the specific B2/B3 blocker it awaits.

**Finding:** the scaffold's schema and interfaces are structurally capable of accepting B3 data once governance decisions are released — this is a genuine, verified readiness fact about the *scaffold*, separate from and not evidence of readiness of the *data sources themselves* (see Section 18's explicit separation, and the Final Adjudication Rule's own instruction not to conflate the two).

## 14. Scan Reproducibility

Per-dimension status, each cross-referenced to the relevant blocker:

| Dimension | Fixable/reproducible today? | Blocker |
|---|---|---|
| Universe | No | B3-01 |
| As-of date | No (depends on trading calendar) | B3-07 |
| Market-data source | No | B3-08 |
| Historical window | No (proposed value only; no data to apply it to) | B3-05 |
| Benchmark | No | B3-03 |
| Sector map | No | B3-04 |
| Corporate-action basis | No | B3-05 (same root gap) |
| Trading calendar | No | B3-07 |
| Data-quality rules | Partially — the rule *shapes* and *vocabulary* are fixed (Section 11), but key thresholds (minimum history, volume usability) are PROPOSED, not authoritative | B2-side, cross-referenced |
| Source/version metadata | Yes, structurally (schema columns exist) — but nothing to record yet | B3-08 |

Every dimension needed for a deterministic scan is currently either undefined or unauthoritative. No scan performed today could be reproduced by a second run, because there is nothing yet to fix as the second run's starting condition.

## 15. B2 Dependency Map

| B2 Component | B3-Satisfied | B3-Blocked | B2-Only | Both | Not Applicable |
|---|---|---|---|---|---|
| Trend | | X | | | |
| Momentum | | X | | | |
| Relative Strength | | | | X | |
| Volume | | X | | | |
| Structure/Breakout | | X | | | |
| 52-week completeness (`w52_complete`) | | X | | | |
| `expected_asof_date` (trading calendar) | | X | | | |
| Benchmark (D03/D04) | | | | X | |
| Sector/context data | | X | | | |
| Composite missing-component rule (D07/D08) | | | X | | |
| Candidate cutoff (D11) | | | X | | |
| Watchlist size (D12) | | | X | | |
| Classification triggers (D10) | | | X | | |
| Reason-code triggers (D16) | | | X | | |
| Ranking/tie-break (D14) | | | X | | |

Reasoning: Trend, Momentum, and Volume are technically B2-only *formula* decisions, but they are marked B3-BLOCKED here rather than B2-only because none of them has any real equity data to operate on regardless of formula approval — the practical blocker today is data absence, not just threshold approval. Structure/Breakout and `w52_complete` are B3-BLOCKED for the same data-absence reason plus the undefined trading calendar. Relative Strength and the benchmark question are BOTH B2 (band values, D03/D04's HUMAN-DECISION on which index to use) and B3 (no benchmark series exists regardless of which index is chosen). Sector/context data is B3-BLOCKED (no taxonomy or mapping). Composite policy, candidate cutoff, watchlist size, classification, reason codes, and ranking are B2-ONLY: they are pure scoring/decision-rule questions that do not require any B3 data to resolve on paper (though real numbers to test them against would still need B3 data later) — none of these was promoted to authoritative status by this audit.

## 16. Implementation Readiness Matrix

| B3 Requirement | Evidence | Status | Dependency | Implementation Impact |
|---|---|---|---|---|
| NIFTY 500 constituent list | Repository-wide search, no file found (Section 4) | MISSING | B3-01 | Blocks `_load_universe()` entirely; no scan can start |
| Constituent effective/as-of date | No list exists to date | NOT APPLICABLE | B3-01 | Moot until B3-01 resolved |
| Symbol/instrument mapping rules | No governing document defines them (Section 5) | MISSING | B3-02 | Blocks reliable joining of universe to any market-data feed |
| Benchmark instrument selection | B2 spec D03/D04 marks NIFTY 500 as PROPOSED, not approved (Section 6) | UNRESOLVED | B3-03 (+ B2 D03/D04) | Blocks Relative Strength entirely regardless of universe |
| Benchmark historical data | Only NIFTY 50 (wrong index) available, 120 sessions (Section 6) | MISSING | B3-03 | Same as above |
| Sector taxonomy + mapping | No taxonomy or mapping found (Section 7) | MISSING | B3-04 | Blocks sector context feature and any sector-level dashboard rollup |
| Equity daily OHLC history | No equity price series found anywhere (Section 8) | MISSING | B3-05 | Blocks Trend, Structure/Breakout, and any component needing `close`/`high`/`low` |
| Equity volume history | No equity volume series found; only zero-valued index volume exists (Section 9) | MISSING | B3-06 | Blocks Volume component entirely |
| 252-bar structural history | No equity series reaches 252 bars; only real series is 120 sessions of the wrong instrument (Section 10) | MISSING | B3-05 (cross-ref) | Blocks Structure/Breakout and `w52_complete` |
| Trading-calendar source | D18 explicitly flagged unresolved in B2 spec; no calendar file/library reference found (Section 11) | MISSING | B3-07 | Blocks STALE detection and `expected_asof_date` |
| Vendor/source authority | Upstox and yfinance are both present as capabilities, neither authorized as a B3 source (Section 12) | UNRESOLVED | B3-08 | Blocks any real data acquisition step |
| Corporate-action adjustment method | Acceptance-gate requirement stated (G2); no method/source named for any candidate vendor | MISSING | B3-05 (cross-ref) | Blocks acceptance-gate enforcement for any real price series |
| Persistence schema for B3 data | `equity_intel/persistence/schema.py` DDL inspected and unchanged this session (Section 13) | SATISFIED | None | Schema can accept data once sourced; not itself a data-readiness fact |
| Repository interfaces for B3 data access | `equity_intel/persistence/repositories.py` inspected, all abstract, unchanged (Section 13) | SATISFIED | None | Interfaces ready to be implemented once a vendor is authorized |
| Data-quality validation mechanism | `equity_intel/validation/framework.py` inspected, vendor-agnostic, configurable, unchanged (Section 8/11) | SATISFIED | None | Ready to validate real data once supplied; carries no data of its own |
| Scan reproducibility as a whole | Section 14 dimension-by-dimension review | BLOCKED | B3-01, B3-03, B3-04, B3-05, B3-06, B3-07, B3-08 | No scan today could be reproduced |

## 17. B3 Blocker Register

**B3-01**
Requirement: An authoritative, reproducible NIFTY 500 constituent list with symbol identity and an as-of date.
Evidence: No such file exists anywhere in the repository (Section 4); no B3 decision document names a source.
Why it blocks B3: Without a universe, no instrument can be scanned; this is the root dependency for every other requirement.
Dependency: None (root blocker).
Exact decision/source needed: A human decision naming the constituent-list source (vendor, static file, or index-provider feed), its symbol format, and its as-of/revision policy.
Blocker type: Governance + source.

**B3-02**
Requirement: A defined symbol/instrument mapping policy (exchange symbol, vendor ticker, renamed/delisted/duplicate handling, corporate-action identity continuity).
Evidence: No governing document defines any of these rules (Section 5).
Why it blocks B3: Without mapping rules, a constituent list (even once sourced) cannot be reliably joined to a market-data feed.
Dependency: B3-01 (a mapping needs something to map).
Exact decision/source needed: A human decision defining the mapping rules, likely alongside the universe-source decision.
Blocker type: Governance + source.

**B3-03**
Requirement: An authoritative benchmark instrument, source, and historical series for Relative Strength (B2 D03/D04).
Evidence: B2 spec marks the benchmark choice HUMAN-DECISION/unapproved; only a NIFTY 50 (not NIFTY 500) 120-session index series exists in the repository (Section 6).
Why it blocks B3: Relative Strength cannot be computed for any stock without a benchmark series, independent of universe or vendor resolution.
Dependency: None directly (parallel to B3-01), though practically resolved alongside vendor selection (B3-08).
Exact decision/source needed: A human decision naming the benchmark index and its data source.
Blocker type: Governance (B2-side choice) + source (B3-side data).

**B3-04**
Requirement: An authoritative sector taxonomy and symbol-to-sector mapping.
Evidence: No taxonomy or mapping file found anywhere (Section 7); B2's own context-feature material leaves GICS vs. NSE-native unresolved.
Why it blocks B3: Sector context (a documented Equity Intelligence feature) cannot be populated or displayed without it.
Dependency: B3-01 (needs a universe to map).
Exact decision/source needed: A human decision naming the taxonomy and its source.
Blocker type: Governance + source.

**B3-05**
Requirement: Daily OHLC price history (adjusted, corporate-action-aware) for every NIFTY 500 constituent, sufficient for at least the 200-252-bar windows the B2 spec's (unauthoritative) components propose.
Evidence: No equity price series of any kind exists in the repository; the only real series is a 120-session NIFTY 50 index feed (Sections 8, 10).
Why it blocks B3: Trend, Structure/Breakout, and `w52_complete` cannot be computed for any real stock.
Dependency: B3-01, B3-02, B3-08 (need a universe, a mapping, and a vendor before data can even be requested).
Exact decision/source needed: Vendor selection (B3-08) plus an explicit acquisition decision (out of scope for this audit to make).
Blocker type: Data + source.

**B3-06**
Requirement: Daily equity volume history meeting the (proposed, unauthoritative) usability rule.
Evidence: The only real series in the repository has zero volume on every bar (index-feed convention, re-confirmed); no equity volume data exists (Section 9).
Why it blocks B3: The Volume component cannot be computed for any real stock.
Dependency: Same as B3-05.
Exact decision/source needed: Same as B3-05; tracked separately because a vendor could in principle supply adequate prices but inadequate volume.
Blocker type: Data + source.

**B3-07**
Requirement: An authoritative NSE trading-calendar source for `expected_asof_date` derivation and STALE detection.
Evidence: B2 spec's own decision register (D18) states this is "not resolvable from the sources"; no calendar file or library reference was found anywhere in the repository.
Why it blocks B3: Without it, STALE status and `expected_asof_date` cannot be assigned deterministically (Section 11), and scan reproducibility (Section 14) fails on this dimension regardless of data availability.
Dependency: None (independent of universe/vendor).
Exact decision/source needed: A human decision naming a trading-calendar source (an NSE holiday API, a maintained static list, or a vendor-supplied calendar).
Blocker type: Governance + source.

**B3-08**
Requirement: An authoritative, approved market-data vendor/source for NIFTY 500 daily bars, benchmark data, and (if bundled) sector/corporate-action metadata.
Evidence: Upstox and yfinance both exist as technical capabilities in the repository (token infrastructure, installed library) but neither is named authoritative by any B3-level decision; G2 only conditionally permits yfinance "if explicitly enabled and tagged" (Section 12).
Why it blocks B3: No data can be legitimately acquired without a designated source, and acquiring data from an unauthorized source would itself be an undisclosed B3 decision, which this audit and prior tasks are instructed never to make silently.
Dependency: None (parallel root blocker alongside B3-01).
Exact decision/source needed: A human decision selecting and formally authorizing a vendor (or a precedence-ordered set of vendors) for B3 purposes specifically.
Blocker type: Governance + source.

## 18. Technical Scaffold vs Release Readiness

**A. Technically buildable scaffold** — Already built and re-verified unchanged this session: package structure, data contracts, pure indicator math, scoring/classification interfaces (no logic), state enum, persistence schema (DDL only, no live database), abstract repository interfaces, a non-functional scanner shell, import-boundary and execution-isolation tests, and a vendor-agnostic validation framework. None of this required any B2 or B3 decision to exist, and none of it was modified by this audit.

**B. Governance-permitted** — Under the current freeze and B1 exception, the scaffold above was permitted to be built (and was, in the prior task). Nothing further is governance-permitted to build right now: B2 remains RELEASE BLOCKED and B3 remains BLOCKED, so no scoring logic, universe loader, vendor integration, or dashboard change is currently authorized.

**C. Source-ready** — NOT ready. Zero of the eight blockers in Section 17 are resolved. No NIFTY 500 universe, benchmark, sector map, equity price history, equity volume history, trading calendar, or vendor authorization exists anywhere in the repository or governing material.

**D. Implementation-ready** — NOT ready. Every one of B3-01 through B3-08 must be resolved by an explicit human governance decision (naming a universe source, a mapping policy, a benchmark, a taxonomy, a vendor, and a trading calendar) before real B3 implementation can begin; in addition, B2's own numeric thresholds (Section 15's "B2-only" and "Both" rows) remain separately unresolved and would still block full scoring even if every B3 item above were resolved today.

These four answers are deliberately kept separate per this audit's instructions: the existence of A and B does not imply C or D, and this audit does not treat scaffold completeness as evidence of data-source readiness.

## 19. Explicit Non-Actions

This audit did not: acquire NIFTY 500 data; download any constituent list; modify any data file; populate `equity_intel.db` (which still does not exist); modify scanner logic; implement any part of B3; implement scoring; implement candidate selection; implement watchlist selection; modify dashboard routes; modify `main.py`; modify `continuous_engine.py`; modify OMS, risk-manager, or broker code; modify strategies; modify `config/symbols.py`; modify any B2 threshold; release B2; release B3; run pytest; run the application; or attempt to repair the previously-refused `equity_intel/**/__pycache__` deletion (out of scope per this task's instructions, not retried or investigated).

## 20. Final Adjudication

**B3 BLOCKED**

Eight concrete, independently-tracked blockers (B3-01 through B3-08) prevent B3 implementation: no NIFTY 500 universe source, no symbol-mapping policy, no benchmark source, no sector taxonomy, no equity price history, no equity volume history, no trading-calendar source, and no authorized market-data vendor. The neutral `equity_intel` scaffold's existence and structural soundness is not treated as evidence of B3 data-source readiness, per this audit's explicit instruction. B3 is not released by this document.

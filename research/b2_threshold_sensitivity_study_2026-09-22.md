# B2 Threshold Sensitivity / Reasonableness Study
Date: 2026-09-22
Status: READ-ONLY / EVIDENCE ONLY

## 1. Governance State
B1: PASS (commit `03ccce95ff47af479d9382723ae91694d39fb6a2`)
B2: DRAFT COMPLETE (per `B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md`), all thresholds PROPOSED — NOT APPROVED
B2 Released: NO
B3: BLOCKED (no NIFTY 500 universe/instrument data released)
Implementation: NOT STARTED
Paper Trading Only: YES — this study places no orders, computes no live signals, and does not touch `core.oms`, `brokers/`, `strategies/`, or the dashboard

## 2. Study Objective
Evaluate whether the currently PROPOSED B2 scoring thresholds behave in a mechanically sane way (correct ranges, monotonic bands, no degenerate boundary behavior) and, where real data permits, observe how the proposed rules behave on it. This is evidence for a later human sign-off decision (Section 18 of the B2 specification). It approves nothing.

## 3. Sources Examined
- `B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md` (session output area; the sole source for every proposed numeric value studied here)
- `B2_SCORING_THRESHOLD_ADJUDICATION_2026-09-21.md` (session output area; confirms no authoritative threshold source exists in the repository)
- `docs/development_freeze_policy.md` at HEAD `03ccce95ff47af479d9382723ae91694d39fb6a2` (B1/B2/B3 governance state)
- `config/symbols.py` (repository universe definition — read to check for any NIFTY 500 constituent data)
- `data/historical/` (repository historical-data directory — read to check for any usable price series)
- `data/*.db`, `core/oms/*.db`, `backups/*/oms_state.db` (repository database inventory — read (schema/location only) to confirm none is an equity-intelligence store)
- `research/` directory listing (checked for any prior NIFTY 500 or per-stock research output)

## 4. Available Data
Date Range: 2026-01-27 to 2026-07-22 (120 daily sessions when 15-minute bars are resampled to daily) — this is the only OHLC price series found anywhere in the repository.
Universe: NIFTY 50 index only (`NSE_INDEX|Nifty 50`, from `config/symbols.py`). No NIFTY 500 constituent list, ticker map, or per-stock series exists anywhere in the repository.
Symbols: 1 (the index itself). `config/symbols.py` defines exactly three tradeable instruments — `NIFTY`, `BANKNIFTY`, `SENSEX` — all indices for the options system; none is an equity.
Observations: 3,001 fifteen-minute bars → 120 resampled daily closes for the NIFTY 50 index. All other `data/historical/` content is either intraday NIFTY-index bars (`NIFTY_1minute.csv`, `NIFTY_5minute.csv`) or single-day NIFTY option-contract minute bars (389 files under `data/historical/options/`, e.g. `NIFTY_2026-03-10_23850_CE_1minute.csv`) — none of these is equity or NIFTY-500-relevant.
Data Limitations:
- **No NIFTY 500 equity data exists in the repository in any form** — no daily bars, no per-stock identifiers, no sector map, no ISIN/instrument-token mapping. B3 (universe) is genuinely blocked, not just administratively blocked.
- **No benchmark series independent of a candidate stock exists.** The only index series available is NIFTY 50 (not NIFTY 500, which D03 of the B2 spec proposes as the benchmark). Relative Strength as specified cannot be computed even illustratively without a second, distinct series.
- **Volume is zero on every bar of the only available series** (index feed convention, not a data error — confirmed by scanning the full `volume` column of `NIFTY_15minute.csv`). Volume/RVOL cannot be computed on any available data.
- **Only 120 daily sessions are available** — short of the 252-bar 52-week window (Structure/Breakout, D05) by 132 sessions, and short of the 200-bar Trend minimum (D01) by 80 sessions. Only Momentum (needs 15 bars) is computable end-to-end on this series.
- No sector taxonomy or classification metadata exists anywhere in the repository.
- Existing `*.db` files (`oms_state.db`, `production_trading.db`, `trading_journal.db`, and their dated backups) are options-system operational stores; none contains equity price history. `data/equity_intel.db` does not exist (consistent with B2/B3 being blocked and no implementation having started).

**Consequence for this study:** a cross-sectional, NIFTY-500-scale empirical sensitivity study (score distributions across hundreds of stocks, candidate-cutoff population sizes, sector concentration, watchlist-K comparisons) is **not possible** from data that exists in this repository today. Sections 6–15 below are explicit about which sub-questions are therefore `NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`, which are answered with data-independent (`DERIVED`) mathematical analysis of the proposed bands themselves, and which are answered with a small amount of genuine `OBSERVED` evidence from the one real series that does exist (NIFTY 50 index, daily-resampled, N=1 instrument — explicitly not a NIFTY 500 sample and not treated as one).

## 5. Proposed Threshold Inventory
All values below are `PROPOSED — NOT AUTHORITATIVE`, sourced solely from `B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md`.

- D01 Trend: EMA 20/50/200, 5 tests × 4 pts, lag 10 bars, min 200 bars — PROPOSED — NOT AUTHORITATIVE
- D02 Momentum: RSI14 bands [<40:0, 40–50:2, 50–55:4, 55–60:6, 60–70:8, ≥70:10]; ROC10 bands [≤0:0, 0–2:2, 2–4:4, 4–6:6, 6–10:8, ≥10:10]; min 15 bars — PROPOSED — NOT AUTHORITATIVE
- D03 Relative Strength: NIFTY 500 benchmark, 60-bar window, rp60 bands [<−5:0, −5…−2:4, −2…0:8, 0…3:12, 3…6:16, ≥6:20]; benchmark failure ⇒ scan ABORT — PROPOSED — NOT AUTHORITATIVE
- D04 Volume: RVOL20 (current bar excluded from denominator) bands [<0.8:0, 0.8–1.0:4, 1.0–1.5:8, 1.5–2.0:12, 2.0–3.0:16, ≥3.0:20]; usability ≥15 of prior 20 bars with volume>0 — PROPOSED — NOT AUTHORITATIVE
- D05 Structure/Breakout: 252-bar 52-week high (incl. current bar); dist52 bands [0–2:12, 2–5:9, 5–10:6, 10–20:3, >20:0]; PH20/PH50 breakout [C>PH50:8, C>PH20:4, else:0]; no fallback when `w52_complete=0` — PROPOSED — NOT AUTHORITATIVE
- Composite = exact sum of the five components, 0–100 — PROPOSED — NOT AUTHORITATIVE (structure sourced; the five band tables feeding it are not)
- Candidate cutoff = composite ≥ 70 — PROPOSED — NOT AUTHORITATIVE (no source basis at all)
- Watchlist K = top 10 eligible candidates — PROPOSED — NOT AUTHORITATIVE (no source basis at all)
- Classification triggers (STRONG_TREND ≥16, WEAK_TREND ≤4, BREAKOUT_WATCH ≥12, MOMENTUM ≥14, RELATIVE_STRENGTH ≥16, VOLUME_EXPANSION ≥12) — PROPOSED — NOT AUTHORITATIVE
- `CTX_ATR_ELEVATED` threshold = atr_pct ≥ 4.0% — PROPOSED — NOT AUTHORITATIVE

## 6. Trend Sensitivity
Observed: On the only available real series (NIFTY 50 index, 120 daily sessions), EMA200 cannot be computed (needs ≥200 sessions; 80 short). No Trend score exists for any session in the available data. `trend_score = None` for all 120 sessions — this is the correctly specified behavior per D01/M2, not a defect.
Derived: Each of the 5 boolean EMA tests is worth exactly 4 points; crossing any single test boundary changes the score by exactly 4 points (out of 0–20), and a day on which multiple relations flip simultaneously (e.g. a gap) can move the score by up to 20 points in one session. The five tests are not independent in general (e.g. `C > E50` and `E50 > E200` jointly influence but do not determine `C > E20`), so the resulting bucket set {0,4,8,12,16,20} will not be uniformly populated across any real population; this is a structural property of the rule, not something this study can quantify further without cross-sectional data.
Limitations: NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA at the population level (score distribution across stocks, clustering frequency, per-bucket occurrence rates) — no NIFTY 500 series exists, and the one series available is too short for EMA200.

## 7. Momentum Sensitivity
Observed: On the same 120-session NIFTY 50 index series, RSI14/ROC10 are computable from session 15 onward (106 usable sessions). Over those 106 sessions: RSI14 ranged 26.61–64.21 (mean 48.18, median 51.19); ROC10 ranged −9.11%…+8.08% (mean −0.50%, median −0.43%). The resulting Momentum score (RSI points + ROC points, 0–20) ranged 0–14 across those sessions (mean 4.89, median 4.0, population stdev 4.07). Score histogram: {0: 22, 2: 21, 4: 17, 6: 14, 8: 12, 10: 11, 12: 4, 14: 5}. RSI sub-band point histogram: {0: 22, 2: 25, 4: 31, 6: 23, 8: 5}. ROC sub-band point histogram: {0: 60, 2: 23, 4: 14, 6: 4, 8: 5} — the ROC sub-component landed in its lowest band (≤0 → 0 pts) in 60 of 106 sessions (57%), noticeably more concentrated than RSI's sub-bands over this one series and period.
Derived: Every RSI band boundary and every ROC band boundary changes the corresponding sub-score by exactly 2 points (both max out at 10), so the two sub-components are symmetric in per-boundary sensitivity by construction; the difference observed above is a property of this one instrument's price action over this one 6-month window, not of the point scale.
Limitations: This is a single index instrument over one 6-month window, not a NIFTY 500 cross-section — the concentration observed in the ROC sub-band is not evidence about how the rule would behave on 500 individual equities, which typically have different volatility and trend characteristics than a broad index. Cross-sectional momentum-score distribution, concentration, and any claim of "excessive clustering" at the population level are `NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`.

## 8. Relative Strength Sensitivity
Observed: No computation is possible. The B2 spec requires a NIFTY 500 benchmark distinct from the scored stock; the repository contains only one price series in total (NIFTY 50 index), so there is no second series to form a spread against, and no NIFTY 500 benchmark of any kind exists.
Derived: The five `rp60` bands each carry a fixed 4-point step (0→4→8→12→16→20), the most uniform per-boundary jump size of any component in the proposed model; this is a property of the band table alone, independent of any data.
Limitations: `NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA` — no benchmark series, no candidate-stock series, and no NIFTY 500 data exist in the repository. The benchmark-failure behavior specified in D03 (scan ABORT rather than a neutral/zero RS) cannot itself be exercised without a benchmark to fail; it is a design property documented in the specification, not something this study can observe in action.

## 9. Volume Sensitivity
Observed: The only available price series carries `volume = 0` on every one of its 3,001 fifteen-minute bars (confirmed by scanning the full column) — an index feed, not an equity feed. Under the D04/D19 volume-usability rule (≥15 of the prior 20 bars with volume>0), every session of the available series would be classified `DQ_VOLUME_UNUSABLE` and receive `volume_score = None`, never a fabricated zero. This is a genuine, observed confirmation that the "never silently substitute zero for missing/unusable volume" invariant (I6) has a real, non-degenerate case to guard against even in the one dataset in this repository.
Derived: Each RVOL band carries a fixed 4-point step (0→4→8→12→16→20), the same uniform jump size as the RS bands.
Limitations: The single available series cannot exercise the "normal" (non-zero, usable) volume path at all, since it never has usable volume. Real equity volume behavior — distribution shape, how often the ≥15-of-20 usability gate would exclude a stock, whether the RVOL bands cluster observations — is `NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`.

## 10. Structure / Breakout Sensitivity
Observed: `w52_complete=0` for all 120 sessions of the available series (120 < 252). Per D05's explicit no-fallback rule, `breakout_score = None` for every session — again the correctly specified behavior, not a defect. Separately, with the 20D/50D highs computed from the available data: on the last available session, `PH20 = PH50 = 24,530.90` and the close was `23,991.05`, so neither the 20-day nor 50-day breakout condition was met on that specific day (illustrative of the mechanics only, on an index, not a NIFTY 500 stock).
Derived: The `dist52` bands are the only component in the model whose points *decrease* as the input increases, in fixed 3-point steps (12→9→6→3→0); the breakout add-on (0/4/8) is the single largest one-boundary jump of any rule in the entire proposed model (8 of a possible 20 points in one component, and 8 of a possible 100 points in the composite) at the moment a stock's close crosses its trailing 50-day high.
Limitations: No series in the repository has ≥252 sessions, so the 52-week component of Structure/Breakout cannot be exercised on any available data, real or otherwise. Population-level frequency of 20D/50D breakout conditions, and any interaction between the 52-week and shorter-term sub-scores, are `NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`.

## 11. Composite Score Distribution
`NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA` at the composite level. A composite requires all five components to be non-`None` simultaneously (D07/D08); on the only available series, Trend, Relative Strength, Volume, and Structure/Breakout are `None` on every session (Sections 6, 8, 9, 10), so `composite_score = None` for all 120 sessions — there is no session in the repository's data on which a composite could legitimately be computed under the proposed rules. This is itself an observation: it demonstrates the D07 "no partial sum" rule is not vacuous — it actively suppresses a would-be score on 100% of the one real series this repository holds. No median, mean, standard deviation, percentile, min/max, or above-cutoff percentage can be reported because no composite value exists to describe. Producing synthetic or fabricated composite values to populate this section would misrepresent a design proposal as empirical fact and is not done here.

## 12. Component Contribution / Correlation
`NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`. Cross-component correlation requires multiple simultaneously-valid components across many observations (ideally many stocks and sessions); the repository provides at most one component (Momentum) as computable, and only for one instrument. No correlation coefficient, dominance measure, or contribution-share statistic can be honestly computed from a single component's series.

## 13. Candidate Cutoff Sensitivity
`NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`. Since no composite score exists anywhere in the available data (Section 11), no candidate population can be formed at cutoff 60, 65, 70, 75, or 80, and no per-date, per-sector, or per-symbol concentration can be measured. Reporting any of these numbers would require inventing a composite-score population that the repository's data does not support. The proposed cutoff of 70 remains a bare, unsupported placeholder (as already stated in the B2 specification's own decision register, D11: `AUTHORITY: NONE`, `STATUS: UNRESOLVED`).

## 14. Watchlist K Sensitivity
`NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`, for the same reason as Section 13 — no candidate population exists to draw a top-5/10/15/20 slice from. The proposed K=10 remains a bare, unsupported placeholder (B2 spec D12: `AUTHORITY: NONE`, `STATUS: UNRESOLVED`).

## 15. Classification / Reason-Code Observations
`NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA`. Classification tags and most reason codes are gated on component scores that are `None` throughout the available data (Trend, Relative Strength, Volume, Structure/Breakout); only Momentum-derived reason codes (`R_RSI_EXPANSION`, `R_ROC10_STRONG`, `R_RSI_WEAK`) could in principle be evaluated on the 106 usable Momentum sessions of the one available series, but doing so on a single non-equity index instrument would not speak to classification-vocabulary behavior across a NIFTY 500 population (over-use of one tag, rare tags, overlap) in any meaningful way, so it is not reported as a population finding here.

## 16. Look-Ahead / Leakage Audit
All feature definitions were inspected against the B2 specification text (not re-implemented as a scanner) for information available strictly as of the observation date:
- **20D/50D highs**: specified as `max(high)` over the 20/50 bars **before** the current bar (window indices `N−21…N−2` / `N−51…N−2`), explicitly excluding the current bar. No leakage.
- **252-bar high**: specified as `max(high)` over the last 252 bars **including** the current bar. This is standard for a "distance below the current 52-week high" measure (the current bar's own high can be part of a new 52-week high) and does not reference any bar after the observation date. No leakage.
- **RSI14 / ROC10**: both defined using only bars up to and including the current bar (`Δ_i` for `i ≤ t`; `roc10 = C_t/C_{t−10} − 1`). No leakage.
- **RVOL20**: denominator is the 20 bars **preceding** the current bar, current bar's own volume is the numerator and is by definition known as of that bar's close. No leakage.
- **Relative returns (rp60)**: both stock and benchmark returns are computed over `[D_ref, D]` where `D` is the scan's `asof_date` (today or the persisted current session) — no future bar is referenced. No leakage.
- The reference computations performed for this study (Sections 7 and 10) used only `pandas`-free, single-pass, forward-only accumulation (Wilder RSI, EMA with a fixed seed window, trailing max for PH20/PH50) — no computation looked past the session being scored.
Conclusion: no look-ahead leakage was found in the specification's feature definitions or in the illustrative computations performed for this study. This audit is of the specification text and of the one series actually computed here; it is not a substitute for reviewing an eventual scanner implementation's code once one exists.

## 17. Data Quality / Coverage Limitations
- Dataset source: repository-local CSV files under `data/historical/`; no external data was fetched for this study (WebFetch/WebSearch were not used; no network calls were made).
- Date range: 2026-01-27 to 2026-07-22, 120 daily sessions (resampled from 15-minute bars).
- Symbol count: 1 (NIFTY 50 index). Zero NIFTY 500 equities.
- Missing observations: none within the available NIFTY 50 series (no gaps detected in the 3,001-row 15-minute file for the covered range); the gap is coverage breadth (1 instrument, 120 sessions), not missing rows within that instrument.
- Stale observations: not assessed — staleness is defined relative to a scan's `asof_date`, and no scan exists.
- Failed observations: not applicable — no scan exists to produce a FAILED status.
- Insufficient-history observations: 120 of 120 sessions are INSUFFICIENT_HISTORY under D08/D09 (w52_complete=0 throughout; also short of the 200-bar Trend minimum for the first 199 sessions, which is all of them).
- Volume availability: zero across the entire available series (index feed convention).
- Benchmark availability: none — no NIFTY 500 index series exists in the repository.
- Corporate-action limitations: not assessed — the available series is an index (not adjustable for corporate actions in the equity sense) and no equity series exists to check.
- Whether 252 trading days are actually available: **no** — 120 available, 132 short.
- Survivorship/universe limitations: total — there is no NIFTY 500 universe of any kind in this repository (confirmed by inspecting `config/symbols.py`, which defines exactly three index instruments for the options system, and by a repository-wide search for equity ticker/OHLC files, which found none).
- Look-ahead concerns: none found in the specification text or in this study's illustrative computations (Section 16).
- Other material limitation: this study could not and did not claim NIFTY 500 coverage anywhere above; every population-level finding requested in the task is explicitly marked `NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA` rather than approximated or simulated as if it were real market evidence.

## 18. Decision Evidence Matrix

Decision ID: D01 (Trend)
Current Proposal: EMA 20/50/200, 5 tests × 4 pts, min 200 bars (PROPOSED — NOT AUTHORITATIVE)
Observed Evidence: Not computable on available data (120 sessions < 200-bar minimum)
Sensitivity Result: Per-boundary jump = 4 pts per test, data-independent (DERIVED)
Material Limitation: No NIFTY 500 data; only series available is too short for EMA200
Decision Status: HUMAN DECISION REQUIRED

Decision ID: D02 (Momentum)
Current Proposal: RSI14 + ROC10 bands, min 15 bars (PROPOSED — NOT AUTHORITATIVE)
Observed Evidence: Computable on 106/120 sessions of one index series; score range 0–14, mean 4.89 (Section 7)
Sensitivity Result: Both sub-bands step 2 pts/boundary (DERIVED); ROC sub-band concentrated at 0 pts in 57% of observed sessions on this one series (OBSERVED, N=1 instrument, not generalizable)
Material Limitation: Single non-equity index instrument, one 6-month window; not a NIFTY 500 sample
Decision Status: HUMAN DECISION REQUIRED

Decision ID: D03 (Relative Strength)
Current Proposal: NIFTY 500 benchmark, 60-bar rp60 bands (PROPOSED — NOT AUTHORITATIVE)
Observed Evidence: Not computable — no benchmark series or second series exists
Sensitivity Result: Bands step uniformly 4 pts/boundary (DERIVED)
Material Limitation: No NIFTY 500 benchmark data of any kind in the repository
Decision Status: HUMAN DECISION REQUIRED

Decision ID: D04 (Volume)
Current Proposal: RVOL20 ex-current-bar, bands, ≥15/20 usability gate (PROPOSED — NOT AUTHORITATIVE)
Observed Evidence: Available series has zero volume on every bar; usability gate would correctly mark it DQ_VOLUME_UNUSABLE on 100% of sessions rather than fabricating a score (OBSERVED)
Sensitivity Result: Bands step uniformly 4 pts/boundary (DERIVED)
Material Limitation: No equity volume data to exercise the "normal" usable-volume path
Decision Status: HUMAN DECISION REQUIRED

Decision ID: D05 (Structure/Breakout)
Current Proposal: 252-bar 52W high, dist52 bands, PH20/PH50 breakout, no fallback (PROPOSED — NOT AUTHORITATIVE)
Observed Evidence: Not computable — 120 available sessions, 132 short of the 252-bar minimum; w52_complete=0 throughout (OBSERVED); illustrative PH20=PH50=24,530.90 vs. close 23,991.05 on the last available session, no breakout (OBSERVED, single index instrument only)
Sensitivity Result: dist52 bands step 3 pts/boundary, decreasing; breakout add-on is the single largest one-boundary jump in the whole model at 8 pts (DERIVED)
Material Limitation: No series in the repository reaches 252 sessions
Decision Status: HUMAN DECISION REQUIRED

Decision ID: Composite (D07/D08)
Current Proposal: Exact sum of five 0–20 components; None if any component missing (PROPOSED — NOT AUTHORITATIVE)
Observed Evidence: composite_score = None on all 120 available sessions (no session has all five components) (OBSERVED)
Sensitivity Result: Not computable — no composite value exists anywhere in available data
Material Limitation: No NIFTY 500 cross-section
Decision Status: HUMAN DECISION REQUIRED

Decision ID: D11 (Candidate cutoff, proposed 70)
Current Proposal: composite ≥ 70 (PROPOSED — NOT AUTHORITATIVE, already flagged UNRESOLVED in the B2 spec)
Observed Evidence: None available — no composite population exists
Sensitivity Result: NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA across 60/65/70/75/80
Material Limitation: No NIFTY 500 cross-section
Decision Status: HUMAN DECISION REQUIRED

Decision ID: D12 (Watchlist K, proposed 10)
Current Proposal: top 10 eligible candidates (PROPOSED — NOT AUTHORITATIVE, already flagged UNRESOLVED in the B2 spec)
Observed Evidence: None available — no candidate population exists
Sensitivity Result: NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA across 5/10/15/20
Material Limitation: No NIFTY 500 cross-section
Decision Status: HUMAN DECISION REQUIRED

Decision ID: D10 (Classification / reason codes)
Current Proposal: Fixed trigger thresholds per component (PROPOSED — NOT AUTHORITATIVE)
Observed Evidence: Only Momentum-gated codes are theoretically evaluable on one non-equity series; not reported as a population finding
Sensitivity Result: NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA
Material Limitation: No NIFTY 500 cross-section, no sector data
Decision Status: HUMAN DECISION REQUIRED

This matrix intentionally contains no approval, no recommended value, and no ranking of alternatives.

## 19. Human Decisions Still Required
All nineteen items in Section 18 of `B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md` (D01–D19) remain open, unchanged by this study. In particular, and unchanged by anything observed here:
- The candidate cutoff value (currently a proposed 70, with no evidentiary basis).
- The watchlist size K (currently a proposed 10, with no evidentiary basis).
- Every band boundary and point value for all five components.
- The choice of NIFTY 500 as the Relative Strength benchmark.
- The composite missing-component rule (`None`, D07).
- The classification trigger thresholds and reason-code vocabulary.
- The `expected_asof_date` / trading-calendar derivation (D18) and the volume-usability count (D19).
- Whether and how the NIFTY 500 universe and per-stock daily history will actually be acquired (B3), without which none of the above can be empirically tested even in the future using this repository's current tooling.

## 20. What This Study Does NOT Establish
This study does not establish:
- optimal thresholds for any component, the composite, the candidate cutoff, or the watchlist size;
- predictive profitability of any proposed rule;
- suitability for live trading (this system remains paper-only; no live-trading readiness claim is made or implied);
- release of B2 (B2 remains blocked pending human sign-off);
- readiness of B3 (B3 remains blocked; no NIFTY 500 universe or equity data exists in the repository).

## 21. Repository Safety
Implementation Started: NO
B2 Released: NO
B3 Released: NO
Files Modified Outside Study: 0
Files Staged: 0

## 22. Final Adjudication

B2 REMAINS BLOCKED — HUMAN DECISIONS REQUIRED

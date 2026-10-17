# Equity dashboard: pending decisions (2026-10-17)

Status: DECISION DOCUMENT ONLY. Nothing here is implemented or approved. No code, schema or data was changed to write
it. `SCORING_STATUS` stays `BLOCKED_B2`. Research / paper only; not a trading recommendation.

Read on branch `equity-intel/adjustment-check` at f91bc5a. Each claim cites the file and line it was read from.

## a) D5: the trading calendar behind the freshness rules

### What the dashboard does now

- The expected session is "the most recent Monday-Friday date whose 18:00 IST cutoff has passed"
  (`dashboard/health.py:46`, judged in `judge_session`, `dashboard/health.py:113`). Holidays are not known.
  `HOLIDAY_CAVEAT` (`dashboard/health.py:35`) and `WEEKDAY_BASIS` (`dashboard/health.py:39`) say so on the page.
- F8 (calendar provenance) is never OK: any stored value, including `UNVERIFIED_INDEX_ONLY`, is shown and judged
  UNKNOWN (`dashboard/health.py:69`, `dashboard/health.py:206`).
- The scanner records `calendar_verification = "UNVERIFIED_INDEX_ONLY"` on every ScanRun. This is frozen by B3-07:
  "Benchmark `NSE_INDEX|Nifty 500` daily candles are the authoritative trading calendar for V1" and "No NSE holiday
  file in V1" (`docs/architecture/equity_intel_scanner_v1_spec.md:45-49`).
- The v1 provisional calendar was decided on 2026-09-26 (`docs/architecture/equity_scanner_v1_design.md:296-300`,
  decision 1). Only "the upgrade to an official NSE calendar (B3-07 proper)" is left open
  (`docs/architecture/equity_scanner_v1_design.md:8-11`).
- That design file points at `research/b3_07_v1_provisional_calendar_decision_2026-10-03.md`. That file is not in this
  checkout (checked with `ls`), so the reference dangles.

### The candidate: calendar v1

- `research/ml/calendar/nse_equity_calendar_v1.csv`: columns `date, weekday, is_session, session_type,
  closure_reason, holiday_master, source`. Manifest status `VALIDATED`
  (`research/ml/calendar/calendar_manifest_v1.json:4`), span 2011-01-01 to 2026-10-02
  (`calendar_manifest_v1.json:5-8`, `research/ml/calendar/validation_report_v1.md:5`), 3,904 sessions, output sha256
  `7babff066e13c8137d10fbabb03246d95b8779b0363affe6287e4ddd1d183e72`
  (`research/ml/calendar/validation_report_v1.md:7`).
- NSE sources decide what a session is (holiday master plus circulars); vendor bars are only a cross-check
  (`research/ml/calendar/README.md:21-24`).
- README: "Not yet used anywhere. Adopting this calendar in the dashboard or in `equity_intel` is a separate change"
  (`research/ml/calendar/README.md:49`).

### What must be decided

1. **Which source.** Calendar v1, or another source. If another, its format must at least give one row per date with an
   is-session flag, and a hash that can be checked before use.
2. **Range.** v1 ends 2026-10-02. The dashboard's expected session today (2026-10-17) is 2026-10-16, which is outside
   the file, so every freshness state would be UNKNOWN or fall back to the weekday rule. Decide:
   - how far past the last stored date the file must run, and how often it is refreshed;
   - what the page shows beyond coverage: UNKNOWN, or the current weekday rule with its caveat.
3. **Which holiday file.** The saved NSE holiday master for 2026
   (`research/ml/calendar/sources/nse_holiday_master/trading_2026.json`, fetched 2026-10-03 per
   `research/ml/calendar/sources/fetch_log.json`) has 20 Capital Market (`CM`) rows, of which 5 fall on or after
   2026-10-03. It cannot cover circular-only exceptions (extra sessions, Muhurat) published after that fetch.
   Needed from you: the extended v2 file with its manifest, or a yes to re-run `fetch_sources.py` and
   `build_calendar.py` (they fetch from nseindia.com and Upstox over the network; not run here).
4. **What the B3-07 ruling must say.** At least:
   - whether an official-calendar file may be used for display rules only, with ScanRun provenance staying
     `UNVERIFIED_INDEX_ONLY`;
   - which file is authoritative (name, version, sha256);
   - what the dashboard shows when its calendar and the run's index-derived sessions disagree.
5. **A conflict to settle.** `equity_intel_scanner_v1_spec.md:48-49` says "No NSE holiday file in V1". A display-only
   use does not change what a run records, but only you can say whether the clause covers it.

Until then the dashboard keeps the weekday rule and its caveat.

## b) B2 scoring: can the sensitivity study be the threshold source?

**No.** `research/b2_threshold_sensitivity_study_2026-09-22.md` is evidence for a human decision; it sets no
threshold. Its own words:

- Header: "Status: READ-ONLY / EVIDENCE ONLY" (line 3). Section 1: "all thresholds PROPOSED — NOT APPROVED"
  (line 7). Section 2: "It approves nothing" (line 14).
- Section 18 ends: "This matrix intentionally contains no approval, no recommended value, and no ranking of
  alternatives." (line 185). Every row reads `Decision Status: HUMAN DECISION REQUIRED`.
- Section 20 ("What This Study Does NOT Establish", line 198) lists "optimal thresholds for any component, the
  composite, the candidate cutoff, or the watchlist size", "predictive profitability of any proposed rule", and "release
  of B2".
- Section 22 (line 213): "B2 REMAINS BLOCKED — HUMAN DECISIONS REQUIRED".

**What it does establish.** The proposed bands step by fixed jumps (derived), the specification text has no look-ahead
(Section 16), and the "no partial sum" and "never substitute zero" rules act on the one real series it had.

**What it does not.** It tested one instrument, the NIFTY 50 index, over 120 sessions, and says so (Section 4). Every
population-level question (composite distribution, cutoff 60 to 80, watchlist K 5 to 20, classification triggers) is
marked `NOT EMPIRICALLY TESTABLE FROM AVAILABLE DATA` (Sections 11 to 15). The cutoff of 70 and K of 10 are
"a bare, unsupported placeholder" (lines 85 and 88). It pre-dates the 486-symbol E4 store, so none of it is
equity evidence.

**What a threshold source document would need.** A document that approves values, with the source of each, from you.
The 19 items D01 to D19 stay open (Section 19, line 187). This study closes none of them.

Scoring is not enabled. `SCORING_STATUS_BLOCKED_B2` is the default in `equity_intel/contracts/scan_run.py:22`.

## c) E4 as-of date: the "not recorded" value

State on the real DB (read-only): all four COMPLETE E4 scans have a stored `asof_date`
(`e4_scan_runs`: 2026-09-29, 2026-09-29, 2026-10-01, 2026-10-01). The dashboard shows "not recorded" and an UNKNOWN F2
state only when the stored value is NULL, empty or not an ISO date (`dashboard/health.py:354`,
`dashboard/queries.py:846`). The scanner writes the value once, at completion, as the maximum of the per-symbol last
dates (`equity_intel/features/runner.py:91`, `:117`).

| Option | What it does | Consequence |
|---|---|---|
| 1. Leave as is | A NULL as-of reads "not recorded" and F2 is UNKNOWN. | Honest, and no new evidence is used. Costs nothing. Cannot happen on today's data. |
| 2. Derive from `e4_feature_sets` | `max(last_date)` per scan_id. | Matches the stored value on 4 of 4 scans. Empty exactly when the stored value is NULL. Adds no coverage. |
| 3. Derive from `symbol_acquisition_results` | `max(last_date)` per acquisition run. | Matches on 3 of 3 acquisition runs. Works when feature sets are empty. Not scan-level evidence. |
| 4. Derive from `acquired_benchmark` | `max(trading_date)` per run. | None for one run (`eqdata-20260929T204259`). Unreliable alone. |
| 5. Use `requested_end` | A request date. | Not usable: 2026-10-03 against the data date 2026-10-01. |

Any derived value must be labelled "derived, not recorded". Deciding F2's state (OK, WARN or UNKNOWN) from a derived
date changes what that state means, so the recommendation is to show it beside an UNKNOWN state and not feed it into the
rule. No NULL case exists in the data today, so there is nothing to fix yet. A change would live in
`dashboard/queries.py:833-849` and `dashboard/health.py:348-356`; it needs no schema or scanner change.

## Decisions needed from you

| # | Decision | Needed to unblock |
|---|---|---|
| 1 | Adopt calendar v1 as the display calendar, or name another source | D5 |
| 2 | The v2 file past 2026-10-02 with its manifest, or permission to run the fetch and build | D5 |
| 3 | B3-07 ruling: display-only use, authoritative file, behaviour past coverage | D5 |
| 4 | A threshold source document that approves values | B2 (the study cannot serve) |
| 5 | Whether a derived as-of fallback is wanted (default: no) | E4 as-of |

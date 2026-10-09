# Equity Intelligence Dashboard — Real-Data Acceptance Report

Date: 2026-10-03. Scope: the read-only dashboard (`dashboard/`), six Market &
Data tabs plus the static Research and Gated tabs. Method: a **copy** of
`data/equity_intel.db` (the original was not opened for writing; the copy was
deleted afterwards), checked against independent SQL, then loaded in a browser.

## Status statement (record verbatim)

> **ML Research is in specification / data-preparation status. No predictive
> model has been trained or evaluated. Current historical depth (about 252
> sessions, 486 symbols, today's constituents) is insufficient for the planned
> multi-year research program.**

Nothing on the dashboard may be read as evidence that ML, scoring or trade
setups have been validated. B2 scoring and Trade Research are `GATED`.

## Data identified

| Item | Value |
|---|---|
| Scan run | `scan_20261003T042151` (latest COMPLETE full run), 500 requested |
| E4 scan | `scan-20261002T235219Z-f0525d51`, as of 2026-10-01 |
| E4 acquisition run | `eqdata-20261002T235033Z-168f862f` (500 mapped, 486 persisted, 122,472 observations) |
| Latest closed session of the scan run | 2026-10-01 |
| E4 data quality | 484 `VALID`, 16 `INSUFFICIENT_HISTORY`; 2 possible corporate-action breaks (HEGAM, VEDL — unchanged from the previous E4 scan) |

The E4 scan and the scan run now agree on 2026-10-01: `as_of_matches_run` is
true on the summary, candidates and stock views, and no E4 view shows the
mismatch warning. (An earlier pass found E4 at 2026-09-29; that was fixed by
re-running the E4 acquisition and scan, with no dashboard change. A backup of
the pre-refresh database was kept.)

The Command Center banner reads `OUTDATED (approximate: market holidays not
known)`. This is the documented holiday limitation of `is_outdated`:
2026-10-02 was an NSE holiday, so 2026-10-01 is in fact the latest session.

## Results

Checks 1, 2 and 8 were re-run on the 2026-10-01 data. The other rows are from
the first pass on the same code, plus a browser smoke test after the refresh
(Command Center, Scanner, Stock Intelligence, ML Research, Trade Research; no
console errors other than a missing favicon).

| # | Check | Result |
|---|---|---|
| 1 | ML Research history depth equals independent SQL: 252 sessions, 2025-09-25 to 2026-10-01, 486 symbols, benchmark 341 sessions (2025-05-21 to 2026-10-01) | PASS |
| 2 | Command Center universe 486 (500 requested); data health 482 / 500 clean, 18 with a warning | PASS |
| 2 | Breadth above EMA reconciles to the source rows: EMA 200 155 of 484 (32.0%), EMA 50 72 of 485, EMA 20 53 of 485 | PASS |
| 2 | 252-bar-high statistic reconciles: 1 symbol within 2%, 2 with no value (see finding F2) | PASS |
| 2 | Positive 10-day ROC: 100 of 486 | PASS |
| 3 | Scanner `close` and `ema_long` equal stored rows for 6 sampled symbols; `vs EMA 200 %` recomputed by hand matches; a symbol with no EMA 200 shows `–` | PASS |
| 3 | Sorting by distance from high is consistent across pages 1–5 (500 rows, no duplicates); the 16 rows with no value are last | PASS |
| 4 | Stock Intelligence: last and previous bar and the percent change equal independent SQL for 4 symbols; chart is from the E4 acquisition run | PASS |
| 4 | Chart EMA 20/50/200 equals the stored E4 values (25-symbol sample, 0 mismatches) | PASS |
| 5 | Sector overview: 20 sectors, alphabetical, counts equal the stored mapping | PASS |
| 6 | ML Research shows no metric, prediction or probability; the only database-derived value is the history depth | PASS |
| 7 | Trade Research: all six items `GATED`, no values | PASS |
| 8 | Test suite: 428 passed, 1 skipped (`pytest` from the repo root). `equity_intel/tests` alone is 412 passed, 1 skipped; the other 16 are the existing top-level `tests/`, not new in this change | PASS |
| 8 | Six routes unchanged; `GET` is the only method on any route; POST refused on all | PASS |
| 8 | No import of broker, order, execution or Upstox modules in `dashboard/` | PASS |
| — | Data Quality lists every symbol with a scan or E4 warning, each with a reason | PASS |

## Findings

- **F1 — 14 symbols have no E4 feature row.** All 14 are recent listings
  (e.g. 192–248 observations against the 252 required). All 14 appear in Data
  Quality as `INSUFFICIENT_HISTORY` with the recorded reason. None is silently
  dropped. Indicator filters exclude them, and the Scanner says so.
- **F2 — "at the 252-bar high" was uninformative (fixed).** The distance is
  measured against the highest *intraday high*, so a close essentially never
  equals it: the exact count is 0 of 484 on both the 2026-09-29 and 2026-10-01
  data. The Command Center and Market X-Ray
  now show the 0–2% histogram bucket instead (1 symbol), labelled "a histogram
  bucket, not a signal". The exact count remains in the API as `at_high`.
- **F3 — demerger example.** `TMPV`/`TMCV` (a demerged name) appear with large
  distances from their moving averages. This is the documented limitation
  (demergers are not adjusted by the vendor), not a dashboard error.

## Limitations carried forward

Today's constituents; about one year of history; split-adjusted but not
demerger-adjusted; survivorship present; provisional calendar. See the ML
research specification, section 2.

## Freeze

With this pass the dashboard is considered feature-complete for the current
phase. Further work is the separate track: ML Research Specification approval →
historical data expansion → offline baseline. Trade Research / TGT-SL stays
untouched until its own specification is approved.

The freeze commit contains only the dashboard implementation, its tests and
this report. The draft ML research specification (named on the ML Research
tab) is not part of it and stays on the ML track. The holiday-blind `OUTDATED`
banner is documented above, not fixed: a trading-calendar check belongs to a
later, separately scoped change.

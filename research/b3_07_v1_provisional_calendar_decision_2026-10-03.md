# B3-07: v1 may use the same-run benchmark as its provisional calendar (2026-10-03)

Status: DECISION RECORD. Restates and applies the existing decisions; introduces no new behaviour.
Proposed for confirmation by Akshay (the repo records the underlying decision as Akshay, 2026-09-26).

## Question

May v1 treat the Nifty 500 daily candles returned by the *same acquisition run* as its trading calendar
and as the benchmark for `relative_return`, without an official NSE holiday/session list?

## Decision

**Yes, for v1.** Already fixed in `docs/architecture/equity_scanner_v1_design.md` Section 11 decision 1
(Akshay, 2026-09-26) and `docs/architecture/equity_intel_scanner_v1_spec.md` Section 3 ("frozen"). This note
removes the remaining ambiguity about what that does and does not settle:

1. The calendar is the positive list of dates the benchmark returned in that run
   (`acquired_benchmark`, keyed by `run_id`). It is never computed as weekdays minus holidays; a real session
   fell on Sunday 2026-02-01 (`research/b3_live_evidence_resolution_2026-09-26.md`, Section 2).
2. E4 uses only the benchmark stored under the acquisition run it reads (`features/runner.py`, `acquired_benchmark WHERE run_id=?`).
   It never mixes benchmark rows across runs. A run without `benchmark_status == "OK"` is not eligible for E4.
3. Every output stays labelled `calendar_status = PROVISIONAL` (`calendar_verification = UNVERIFIED_INDEX_ONLY` on
   the scanner side). Nothing may call it an official NSE calendar.
4. Individual stocks never define market-open days. A stock missing a benchmark date is a data-quality matter
   for that stock, not a calendar change.
5. Benchmark fetch failure, empty or unparseable result: the run does not proceed on that basis (scanner: `ABORTED`
   with `CALENDAR_INVALID`; E4: acquisition run not selected).

## What this does not settle

B3-07 as originally defined (an official NSE trading-holiday and special-session source,
`research/b3_live_evidence_resolution_2026-09-26.md` Section 5) is **not** closed: NSE's list loads
dynamically and no structured export was obtained. It is re-scoped from "blocks v1" to
"upgrade path": adopt an official source later and replace `PROVISIONAL`, with no change to the v1 contract.
Known cost of the provisional basis: a benchmark that omits a real session, or includes a non-session, goes
undetected by this pipeline.

## Changes made with this note

- `equity_scanner_v1_design.md`: header and Section 10 item 1 point here instead of reading as undecided.
- `equity_data_acquisition_e1_e3.md`: the limitation line states the decision and the open upgrade path.

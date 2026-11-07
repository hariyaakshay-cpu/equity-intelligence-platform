# Announcement data feasibility - verdict (2026-11-08)

Verdict: **FEASIBLE for a daily (next-open) event study on NSE data, 2021 onward.**
Same-day intraday reaction: NOT testable at scale yet (5-minute cache covers
2025-09-19 to 2026-10-23, 186 symbols).

Evidence: `probe_20261108T005015/` (5 symbols x 6 windows) and
`coverage_20261108T005718/` (market-wide, 15th of every month, 178 days,
2012-01 to 2026-10; see its `timestamp_quality_report.md`).

## A. Can the data be obtained?
- NSE `api/corporate-announcements`: yes. 178/178 market-wide day requests
  returned HTTP 200 without a symbol filter (89-141 companies per day in 2012,
  ~500 announcements per day by 2024). Fields: symbol, ISIN, `desc`
  (category), `attchmntText` (one-line summary), attachment URL, `an_dt`,
  `exchdisstime`.
- BSE `AnnSubCategoryGetData`: no. 12/12 requests returned 403 Access Denied
  (CDN block). Not pursued.

## B. Timestamp quality
- Every record has a time of day in `an_dt` back to 2012 (minute precision
  before ~2020).
- `exchdisstime` (dissemination): 0% of records 2012-2019, 45% in 2020,
  100% from 2021. Seconds precision ~97% from 2021.
- Gap `exchdisstime - an_dt`: median 1-6 seconds; 49 of 51,040 sampled records
  (0.1%) differ by more than 1 hour, up to ~76 days (e.g. MPSLTD takeover
  disclosure: an_dt 2021-04-15, disseminated 2021-06-30). Using `an_dt` there
  would be look-ahead; the pre-registered rule uses `exchdisstime` when present.

## C. History depth and gaps
- Data from at least 2012-01. The 5 empty days in the sample are all exchange
  holidays (2012-08-15, 2013-08-15, 2014-03-17 Holi, 2014-10-15 election,
  2016-08-15). No unexplained gaps.
- Time of day (sample, all years): after 15:30 57%, 09:15-15:30 39%,
  before 09:15 4%. From 2021: after 15:30 ~60%.

## D. Link to first tradeable price
- Defined in the pre-registration (entry = first session whose 09:00 is after
  the event time) and tested in `equity_intel/tests/test_announcement_event_study.py`
  (pre-09:00, 09:00 exactly, market hours, after close, weekend, holiday).
- Checked on real files: e.g. BEL announcement Thu 2015-05-14 18:06 -> entry
  Fri 2015-05-15; Fri 2015-05-08 16:06 -> Mon 2015-05-11. One H5 return
  recomputed by hand from the CSVs matched the module to 6 decimals.

## Consequences for the research plan
- Event study v1 uses daily prices, entries at the next open, DEV 2021-2024,
  HOLDOUT 2025-2026 (pre-registration
  `docs/architecture/announcement_event_study_preregistration.md`, sha256 in
  `event_study_prereg_2026-11-08.sha256`).
- NSE `desc` is noisy: near-duplicate labels exist ("General Updates" /
  "General updates", "Loss of Share Certificates" / "Loss of share
  certificate"). v1 uses them verbatim as frozen; merging is a later version.
- Universe limited to current NIFTY 500 price files (survivorship bias noted).

# Announcement event study v1 - pre-registration

Status: FROZEN 2026-11-08, before any announcement-linked return was computed.
The sha256 of this file is recorded in
`research/announcements/event_study_prereg_2026-11-08.sha256`; the runner
refuses to start if the file no longer matches. Any change = a new version.

## Question

After an NSE corporate announcement of a given type, does buying the stock at
the first open you could actually trade, and selling at a fixed exit, earn more
than the NIFTY 500 over the same window, after costs?

Long only (D2). Paper research only; no orders.

## Data

- Announcements: raw NSE responses saved by `scripts/announcement_coverage_fetch.py
  --all-days`, 2021-01-01 to 2026-10-31. Records missing `symbol` or both
  timestamps are dropped. Duplicates (same symbol, `desc`, `an_dt`,
  `attchmntFile`) are kept once.
- Prices: `data/daily_history_early/` + `data/daily_history/` (daily OHLCV,
  split/bonus adjusted, demergers not adjusted), same sources for the
  `NIFTY500_INDEX` benchmark.
- Trading sessions = dates present in the NIFTY500_INDEX daily files.

## Definitions (frozen)

1. **Event time** = `exchdisstime` (exchange dissemination) when present and
   parseable, else `an_dt`. The source used is recorded per row
   (`ts_source`).
2. **Entry session** = the earliest trading session S such that event time is
   before 09:00 IST on S (time to place an AMO / pre-open order). An event at
   or after 09:00 on S enters on the next session. So events during market
   hours and after the close both enter at the next session's open.
3. **Category** = NSE `desc`, stripped of surrounding spaces, used verbatim.
   No hand classification, no keyword rules, no merging of categories.
4. **Observation unit** = (symbol, entry session, category). Several
   announcements of the same category for the same symbol and entry session
   count once.
5. **Entry price** = open of the entry session.
6. **Horizons** (exit at the close of):
   - H0: the entry session (same-day square-off, intraday),
   - H1: the session after the entry session,
   - H5: the fifth session after the entry session.
7. **Raw return** = exit close / entry open - 1.
   **Abnormal return** = raw return - NIFTY500_INDEX return over the same
   open-to-close window.
8. **Costs** (round trip, subtracted from both raw and abnormal returns):
   - H0: 0.1824% = `round_trip_cost_pct()` of
     `equity_intel/intraday/backtest.py` (ASSUMED schedule, slippage included).
   - H1, H5: 0.35% (delivery; same figure as the 12-1 momentum
     pre-registration).
   Results are labelled "cost model provisional".

## Filters (frozen)

- Symbol must have a daily price file. Universe = the current NIFTY 500
  files present (survivorship bias acknowledged below).
- Liquidity: median of close x volume over the 20 sessions strictly before the
  entry session >= INR 10 crore, with at least 15 of those 20 rows present.
- The stock must have rows for the entry session and the exit session.
- Locked entry: if on the entry session open == high == close, the buy could
  not have filled at the open; the observation is dropped and counted.
- No outlier removal. Observations with |raw return| > 20% are counted and
  reported, not removed.

## Periods

- DEV: entry sessions 2021-01-01 to 2024-12-31.
- HOLDOUT: entry sessions 2025-01-01 to 2026-10-31. Run once, only for
  category x horizon pairs that pass DEV, and never re-run.

## Eligible tests

Every category with >= 300 DEV observations (after filters, counted at H0) is
tested at all three horizons. K = (number of eligible categories) x 3. The list is decided
mechanically by this rule, not by looking at returns.

## Pass rules

Bootstrap: 10,000 resamples of entry sessions (all observations of a resampled
session move together), seed 20261108, statistic = mean net abnormal return.

DEV pass for a (category, horizon), all of:
1. n observations >= 300 and distinct entry sessions >= 60 (D6).
2. Mean net abnormal return > 0 and mean net raw return > 0.
3. One-sided bootstrap lower bound of mean net abnormal return at confidence
   1 - 0.05 / K is > 0 (multiple-testing guard across all K tests).
4. No single symbol contributes more than 10% of the summed positive net
   abnormal return (D6 concentration rule).

HOLDOUT pass, all of:
1. n observations >= 100.
2. Mean net abnormal return > 0 and mean net raw return > 0.
3. One-sided 95% bootstrap lower bound of mean net abnormal return > 0.

A (category, horizon) becomes a candidate live signal only if it passes DEV
and HOLDOUT. Anything else is reported as FAIL with its numbers.

## Known limitations (accepted up front)

- Survivorship: only stocks in today's NIFTY 500 are included; companies that
  left the index are missing. This can bias results upward.
- Events during market hours are measured from the next open, so any same-day
  intraday reaction is not captured by v1 (needs 5-minute history; separate
  study).
- Before about 2021, `exchdisstime` is often missing; DEV starts in 2021
  partly for this reason. Rows that fall back to `an_dt` are counted.
- NSE `desc` is coarse ("Press Release", "Updates"). v1 tests it as-is;
  splitting categories by content is a later, separately registered version.
- Costs are an assumed schedule, not verified against current circulars.

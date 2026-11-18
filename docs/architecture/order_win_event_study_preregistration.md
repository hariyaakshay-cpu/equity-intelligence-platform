# Order-win event study v2 - pre-registration

Status: FROZEN 2026-11-08, before any order-win return was computed. The
sha256 of this file is in `research/announcements/order_win_prereg_2026-11-08.sha256`;
the runner refuses to start if it no longer matches (CRLF normalised to LF).
Any change = a new version.

Context: v1 (`announcement_event_study_preregistration.md`) found no edge in
NSE's own categories; order wins are hidden inside "Updates" / "Press Release".
Before this freeze only counts and sample texts were inspected (no returns):
970 order-win announcements with a rupee amount, 174 companies, 2021-2026.

## Question

When a company announces an order or contract win that is large relative to
its market value, does buying at the first open you could trade and holding
for a fixed period beat the average liquid stock, after costs? Long only.
Paper research only; no orders.

## Data

- Announcements: raw NSE files saved by `scripts/announcement_coverage_fetch.py
  --all-days` (2012-2020 and 2021-2026 runs), loaded with
  `equity_intel.announcements.event_study.load_announcements` (event time =
  `exchdisstime` if present else `an_dt`; duplicates dropped).
- Prices: daily OHLCV from `data/daily_history_early/`, `data/daily_history/`
  and `data/daily_history_orders/` (later directory wins on overlap).
- Shares outstanding: NSE `issuedSize` per symbol, fetched once by
  `scripts/order_win_shares_fetch.py`, saved raw.
- Trading sessions = dates in the NIFTY500_INDEX daily files.

## Order-win extraction (frozen, applied to `attchmntText`, case-insensitive)

An announcement is an order win if ALL of:
1. ORDER matches: `\b(orders?|contracts?|LOA|LOI|letter of (award|acceptance|intent)|work order|purchase order)\b`
2. WIN matches: `\b(receiv\w*|bag\w*|secur\w*|win|wins|won|award\w*)\b`
3. NEG does not match: `\b(tax|gst|demand|penalty|commissioner|tribunal|court|sebi order|show cause|assessment)\b`
4. AMOUNT matches: `(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\b|lakhs?|lacs?)`
   The FIRST match is the order value; lakh/lac values are divided by 100 to
   give crore. Other currencies are not parsed.

Category labels from NSE are ignored.

## Event definition

- Entry session: as v1 - the first session S with event time before 09:00 IST
  on S; entry price = open of S.
- Unit = (symbol, entry session). Several order wins for the same unit -> the
  LARGEST amount is used (the same order is often filed twice).
- Non-overlap: per symbol, units sorted by entry; a unit whose entry is within
  20 sessions after the previous KEPT unit's entry is dropped and counted.
- Market cap (INR crore) = issuedSize x close of the session before entry / 1e7.
- Materiality = order value / market cap.

## Thresholds

- PRIMARY: materiality >= 5%.
- Secondary (reported, never used for a verdict): >= 2% and >= 10%, and all
  order wins regardless of size.

## Horizons and returns

- H0: exit at the close of the entry session.
- H5: exit at the close of the 5th session after entry.
- H20: exit at the close of the 20th session after entry.
- Raw return = exit close / entry open - 1.
- Benchmark (primary): equal-weight mean of the same open-to-close return over
  all stocks in the NIFTY 500 price files with median close x volume over the
  20 sessions before entry >= INR 10 crore (same window, same days). This is
  chosen because v1's one pass was a size/turn-of-quarter effect against the
  cap-weighted index.
- Secondary benchmark (reported only): NIFTY500_INDEX.
- Abnormal = raw - benchmark. Net = minus a flat 0.50% round trip at every
  horizon (conservative: small caps, wider spreads). "Cost model provisional".

## Filters

- Liquidity of the event stock: median close x volume over the 20 sessions
  before entry >= INR 2 crore, with >= 15 of those rows present.
- Rows required for the stock and the index on entry and exit sessions.
- Locked entry (open == high == close on entry) dropped and counted.
- Missing issuedSize -> unit dropped and counted.
- No outlier removal; |raw| > 20% counted and reported.

## Periods

- DEV: entry sessions 2014-01-01 to 2022-12-31.
- HOLDOUT: entry sessions 2023-01-01 to 2026-10-31. Run once, only for
  horizons that pass DEV, never re-run.

## Pass rules

K = 3 (primary threshold x H0/H5/H20). Bootstrap: 10,000 resamples of entry
sessions, seed 20261108, statistic = mean net abnormal return.

DEV pass for a horizon, all of:
1. n >= 300 and distinct entry sessions >= 60.
2. Mean net abnormal > 0 and mean net raw > 0.
3. One-sided bootstrap lower bound at confidence 1 - 0.05/3 > 0.
4. No symbol contributes more than 10% of the summed net abnormal return.

If n < 300 the verdict is INSUFFICIENT_DATA, which counts as FAIL. The minimum
is not lowered.

HOLDOUT pass: n >= 100, mean net abnormal > 0, mean net raw > 0, one-sided
95% bootstrap lower bound > 0.

Candidate live signal only if a horizon passes DEV and HOLDOUT.

## Known limitations (accepted up front)

- Market cap uses today's share count with split/bonus-adjusted prices; share
  issuance (QIP, rights, preferential) between event and today is not
  reflected, so older materiality is approximate.
- 2014-2019 events have `an_dt` only (minute precision, no dissemination
  time); about 0.1% of later records show large gaps between the two.
- The extraction reads only NSE's one-line summary, not the PDF; orders whose
  value is only in the attachment are missed.
- Companies delisted before today may lack prices or shares and drop out.
- Costs are an assumed flat figure, not verified against circulars.

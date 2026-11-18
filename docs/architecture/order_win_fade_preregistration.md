# Order-win fade (intraday short) - pre-registration

Status: FROZEN 2026-11-18 (D1-D7 approved by Akshay), before any 2023-2026
return was computed for this question. The sha256 of this file is in
`research/announcements/order_win_fade_prereg_2026-11-18.sha256`; the runner
refuses to start if it no longer matches (CRLF normalised to LF). Run exactly
once. Any change = a new version.

## Where the idea comes from (disclosed)

Order-win v2.1 DEV (2014-2022, commit 3faeefd) failed as a LONG signal. Its
H0 rows showed the opposite: after an order win >= 5% of market cap, the stock
fell from the entry-day open to the close on average (-0.78% vs the
equal-weight liquid basket before costs, 66% of 309 trades below the basket).
That pattern was found by looking at DEV, so DEV cannot test it. This study
tests it only on data no order-win study has evaluated.

## Question

After a material order win, does SHORTING at the entry-day open and covering
at that day's close make money after costs? Intraday only (MIS-style, square
off same day). Paper research only; no orders.

## Fixed from v2.1 (identical, by reference)

Order-win extraction regexes, amount parsing, entry-session rule (first session
with event time before 09:00 IST), unit definition (largest amount per
symbol/session), 20-session non-overlap, market cap = MCAP Issue Size x prior
close, materiality, event-stock liquidity filter (median value >= INR 2 cr,
>= 15 of 20 rows), equal-weight liquid benchmark (>= INR 10 cr), data runs
(FULL_RUNS), price directories, shares file shares_mcap17112026/shares.csv.

## Decisions (approved 2026-11-18)

- D1 Period: entry sessions 2023-01-01 to 2026-10-31 (the v2.1 HOLDOUT window,
  never evaluated for order wins). Disclosure: v1 (2021-2024 DEV) measured
  NSE category averages ("Updates", "Press Release") that contain some of these
  filings, at category level and long only; no order-win-specific or short
  return was computed. Alternative: 2025-01-01 onward only (fully unseen by
  any study) - cleaner but likely under 100 trades.
- D2 Threshold: materiality >= 5% (same PRIMARY as v2.1). One test, K = 1.
  No secondary thresholds reported until after the verdict.
- D3 Horizon: H0 only - short at the entry-session open, cover at that
  session's close. No multi-day hold (overnight shorts are not allowed in the
  cash market).
- D4 Returns: short raw = -(close/open - 1). Short abnormal = benchmark
  open-to-close return - stock open-to-close return. Net = minus a flat 0.50%
  round trip (same conservative figure as v2.1; real intraday costs are
  lower, but slippage at a news open is not measured).
- D5 Shortability filters: drop the unit if the stock's series in the MCAP
  file is not EQ (BE/BZ and other trade-to-trade series cannot be traded
  intraday; series is today's, not point-in-time - disclosed limitation);
  drop if open == low == close on the entry session (locked, short not
  fillable); drop if open == high == close (as v2.1).
- D6 Pass rule (all required):
  1. n >= 100 trades and >= 40 distinct entry sessions (else
     INSUFFICIENT_DATA = FAIL; the minimum is not lowered).
  2. Mean net short raw > 0 AND mean net short abnormal > 0.
  3. One-sided 95% bootstrap lower bound of mean net short abnormal > 0
     (10,000 resamples of entry sessions, seed 20261118).
  4. No symbol contributes more than 10% of the summed net short abnormal.
- D7 After the verdict: PASS -> candidate signal only, paper-tracked live
  for at least 3 months before any real money; FAIL -> closed, no re-run,
  no threshold/horizon/cost changes, and the order-win line of research ends.

## Known limitations (accepted up front)

- Entry at the official open assumes a short fill at that price; news opens
  can gap and move fast. Not modelled beyond the 0.50% cost.
- Series filter uses today's series; a stock that was BE in 2023 but EQ now
  (or the reverse) is misclassified.
- Same share-count and extraction limitations as v2.1.

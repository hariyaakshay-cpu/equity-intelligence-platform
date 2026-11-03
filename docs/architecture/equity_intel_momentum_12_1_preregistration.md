# 12-1 Month Cross-Sectional Momentum - Pre-Registration (written 2026-11-03 BEFORE any momentum result)

Status: FROZEN at commit (see research/momentum/manifest_2026-11-03.sha256). Nothing below has been computed.

## Why this hypothesis (stated before results)
Chosen from published evidence, not from this repository's data: 12-month return skipping the most recent month is the
standard cross-sectional momentum signal (Jegadeesh-Titman 1993; documented in Indian equities too). It is a different
signal from scoring v0 (which used short-window momentum, volume, breakout, trend, RS and 52-week distance and FAILED
on DEV the same day). It was picked by the owner from three options offered after that result; the 2026-11-03 DEV
replay of scoring v0 is the only result seen on this data. The HOLDOUT window (2025-09-05 .. 2026-10-28) has not been
read by any test.

## Rules (frozen)
- Universe: the 490 symbols in data/daily_history (today's NIFTY 500 list; survivorship-biased, see limits).
- Signal date t: every trading date of the symbol series. For each symbol with bar index k at t:
  score = close[k-21] / close[k-252] - 1. Needs k >= 252.
- Eligible at t: score defined; median(close x volume) over bars k-19..k >= INR 10 crore; forward bars k+1 and k+21 exist.
- Exclusion (suspected unadjusted corporate action): any one-bar close-to-close move beyond +/-30% in bars k-252..k+21.
  Applied to picks (dropped, NOT refilled) and to the benchmark.
- Picks: top 10 eligible by score (tie-break: symbol ascending). Entry = open[k+1], exit = close[k+21] (21 sessions).
- Cohort return = equal-weight mean of kept picks. Net = gross - 0.35% (assumed delivery round trip, full turnover each
  cohort; conservative). Benchmark = equal-weight mean over all eligible non-excluded stocks, same window, no cost.
  Excess = net - benchmark. Secondary (reported only): excess vs NIFTY 500 index close(t+21)/open(t+1) - 1.
- Split by signal date, using the SAME calendar boundaries as the daily study so nothing new leaks:
  DEV = signal dates 2022-10-06 .. 2025-08-05 whose exit date is before 2025-09-05; HOLDOUT = signal dates
  2025-09-05 .. 2026-10-28 with a full 21-session forward window. Dates between are dropped.
- A signal date needs at least 100 eligible stocks (as in the daily replay).

## Decision
- DEV qualifies for HOLDOUT only if mean net excess > 0. HOLDOUT is then run ONCE; the result file is never overwritten.
- HOLDOUT PASS needs all of: mean net excess > 0; lower end of a two-sided 95% circular moving-block bootstrap interval
  > 0 (10,000 resamples, block = 21 signal dates, seed 20261103; one hypothesis, alpha 0.05); >= 100 signal dates;
  no single symbol above 10% of total excess. Max drawdown of the cumulative excess curve is reported, not a gate.
- A PASS means "Stage 4 candidate" only: paper-tracking next, no money, B2 stays open.

## Known limits (stated before results)
- Survivorship bias flatters momentum (losers that left the index are missing). A pass must be read with this first.
- Only ~13 months of HOLDOUT: about 13 non-overlapping holding periods. The test has low power; a FAIL may mean
  "not shown", not "no effect". Overlapping daily cohorts do not add independent evidence (hence the block bootstrap).
- One market regime (2022-2026) may dominate. Turnover is assumed 100% per cohort (real momentum turnover is lower).
- A failed result closes this hypothesis on this data. It is not retuned (no other lookbacks, sizes or holds).

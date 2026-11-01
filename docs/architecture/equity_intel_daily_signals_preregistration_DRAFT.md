# Daily / Swing Signals (short-term and medium-term lists) - Pre-Registration (DRAFT, written 2026-10-28 BEFORE any result)

Status: DRAFT. Nothing below has been run and no daily history beyond the existing 252 sessions has been fetched.
Purpose: find out whether the provisional daily lists (scoring v0, "not B2-authoritative, untested for expectancy") have
any edge after costs, relative to the market. Nine intraday setups failed first; this is a separate hypothesis family.

## What is tested (frozen: scoring code and bands are NOT tuned after results)
- SHORT list: stocks whose scoring-v0 short-horizon score (momentum + volume + breakout) is >= 70% of its maximum.
- MEDIUM list: stocks whose scoring-v0 medium-horizon score (trend + relative strength + 52-week distance) is >= 70%.
- Each signal date t (after the close), each list: take the top 10 by score % (tie-break: symbol). Fewer than 10 is allowed;
  zero picks means no cohort that day. Scores use only bars up to and including t.
- Entry = open of session t+1. Exit = close of session t+H. H = 5 sessions (short list), H = 20 sessions (medium list).
- Eligibility at t: median traded value (close x volume) over the previous 20 sessions >= INR 10 crore.
- Exclusion: a trade is dropped if any one-session close-to-close move beyond +/-30% occurs between t-60 and t+H
  (suspected unadjusted corporate action; Upstox history is split-adjusted but demergers are not). Exclusions are counted and reported.

## Measure
- Cohort return for a signal date = equal-weight mean of that day's picks. Excess return = cohort return minus the
  equal-weight mean of ALL eligible stocks over the same entry/exit window (so a rising market is not counted as skill).
  Secondary report: excess over the NIFTY 500 index.
- Reports show gross and net. Net = gross minus an ASSUMED delivery round-trip cost of 0.35% (STT, stamp, exchange fees,
  brokerage, GST and 5 bps slippage per side; rates not verified). The benchmark is not charged cost. The owner states costs are his own
  responsibility, so the pass test is shown on both but the decision rests on net.

## Protocol
- Needs at least 4 scored years: daily history from 2021-10-01 (fetch script `scripts/equity_daily_history_fetch.py`), with a
  252-bar warm-up before the first valid score.
- Split by signal date: DEV = first 70% of valid signal dates, then a purge gap of H sessions, then HOLDOUT = last 30%. The HOLDOUT is not examined until
  a list shows mean net excess return > 0 on DEV, and is run ONCE per list; the report is final and never overwritten.
- Overlap: cohorts overlap in time, so intervals use a date-block bootstrap with block length >= H (not independent days).
- HOLDOUT pass (per list): mean net excess return > 0, bootstrap lower bound > 0 at alpha = 0.05 / 2 (two lists tested), at least 100 signal dates,
  and no single symbol above 10% of total excess profit. Max drawdown of the cumulative net excess curve is REPORTED, not a gate.
- A pass means "Stage 4 candidate" only. It does not authorise any signal to be sent (B2 stays open) and does not remove the survivorship caveat.

## Known limits (stated before results)
- Survivorship bias: the universe is today's NIFTY 500 (24 Sep 2026 file). Stocks that left the index or were delisted are absent, which flatters any
  momentum-style result. A pass must be read with this stated first; the survivorship audit is only partly done.
- The bands behind the scores are PROVISIONAL proposals, not validated thresholds.
- One market regime may dominate four years of data. Sector concentration is not computed by the current harness.
- Historical scores must be recomputed point in time from candles; this needs a new scoring-replay script, to be written after this document is committed.
- A failed result closes this version. It is not retuned on the same data.

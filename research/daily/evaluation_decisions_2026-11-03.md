# Daily study: evaluation decisions (written 2026-11-03 BEFORE any evaluation result)

The replay (scores + forward returns) was produced first; no cohort, excess or summary statistic had been computed
when this note and the manifest were recorded. These points are not settled by the 2026-10-28 pre-registration text,
so they are fixed here once and not revisited after results.

1. Corporate-action exclusion (+/-30% move, t-60..t+H) removes a stock from the picks AND from the equal-weight
   eligible benchmark for that window.
2. Picks are the top 10 eligible stocks by score at or above 70 BEFORE the exclusion is applied; an excluded pick is
   dropped, not replaced (refilling would use information after t).
3. "Bootstrap lower bound > 0 at alpha = 0.05 / 2": read conservatively as the lower end of a two-sided 97.5% interval
   (1.25th percentile of 10,000 circular moving-block bootstrap means, block length = H signal dates, seed 20261103).
4. Symbol concentration: a symbol's share = sum over its picks of (net return - benchmark) / cohort size, divided by
   total excess; undefined (check fails) if total excess <= 0.
5. Purge gap: the replay script uses 20 sessions for both lists; this is >= H for both (5 and 20), so it meets the
   pre-registered "gap of H sessions" conservatively for the short list.
6. Secondary excess vs the NIFTY 500 index uses index close(t+H) / open(t+1) - 1. Reported only, not a gate.
7. DEV qualification for HOLDOUT is mean net excess > 0 on DEV (as pre-registered); HOLDOUT is run once per qualifying
   list by scripts/equity_daily_eval.py, which refuses to overwrite an existing result file.

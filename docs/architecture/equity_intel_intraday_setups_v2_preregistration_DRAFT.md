# Intraday Setups Round 3 - Pre-Registration (DRAFT, written 2026-10-28 BEFORE any round-3 result)

Status: DRAFT until the owner approves and commits it. Nothing below has been run. Parameters are fixed now and may not
change after results. Rounds 1-2 (six setups) all failed; their mean gross return was about zero (net + 0.18% cost), so cost
was not the main problem: the triggers carry no edge on their own. Round 3 tests whether MARKET CONTEXT and RELATIVE
STRENGTH, which the earlier setups ignored, add one. Positions already exit at the 15:15 bar, so holding longer is not a lever.

## Protocol (unchanged from round 2)
- Same data (186-stock liquid universe, 5-minute bars), same split by date: DEV = first 70% of sessions, HOLDOUT = last 30%.
  The HOLDOUT has not been examined by any round and stays unexamined until a setup passes DEV.
- A setup goes to HOLDOUT only if DEV mean net return per trade > 0. HOLDOUT runs ONCE per setup and the report is final.
- Nine setups will have been tried in total (6 + 3), so the HOLDOUT bootstrap uses Bonferroni alpha = 0.05 / 9, with
  at least 100 trades and 30 sessions, plus the D6 concentration and drawdown limits.
- Costs: the owner states costs are his own responsibility. Reports show BOTH gross and net (assumed COSTS) per trade.
  The pass test stays on net, so a setup cannot pass on a cost assumption the owner has not verified.
- Long only, closed bars, entry = next bar open, exit = 15:15 bar close, max 5 signals/day, tie-break first trigger time then symbol.
- MARKET CONTEXT is computed from the 186 stocks themselves (no index data needed): at bar t, BREADTH = share of stocks whose
  close is above their previous session close; MEDIAN_RET = median of (close / previous close - 1) across the universe.
  Both use only bars up to t.

## Setups (all LONG, version v2)
- R3_BREADTH_ORB_LONG: the unchanged ORB_LONG trigger (3-bar opening range, window to 11:30), taken only if at the trigger bar
  BREADTH >= 0.60 and MEDIAN_RET >= +0.25%.
- R3_RS_LEADER_LONG: first bar between 10:15 and 12:00 where the stock's (close / previous close - 1) >= MEDIAN_RET + 1.0%,
  close >= 0.998 x session high so far, and MEDIAN_RET >= 0.
- R3_VOLUME_SURGE_LONG: first bar between 09:30 and 13:00 where bar volume >= 3 x the stock's median volume for the same
  time-of-day bar over the previous 20 sessions, close > highest high of all earlier bars that session, and close > session VWAP.
  The first 20 sessions of data are excluded for this setup.

## Known limits (stated before results)
- Filtered setups trade less often; one or more may end INCONCLUSIVE (too few HOLDOUT trades) rather than pass or fail.
- About 270 sessions is a short history and may cover a single market regime.
- Sector concentration and walk-forward are not computed by the current backtest harness.
- A failed Round 3 closes this family of ideas; it is not retuned.

# Intraday Setups Round 4 - Pre-Registration (DRAFT, written 2026-10-30 BEFORE any round-4 result)

Status: DRAFT. Nothing below has been run. Rounds 1-3 (nine setups) failed; their gross mean was at most about +0.1% per
trade against an ASSUMED round-trip cost of 0.18%. Hypothesis for this round: the fixed cost matters less on LARGE-MOVE
days, so restrict trading to stocks and days where a large move is already under way. Only two setups are tested, to limit
the multiple-testing penalty. A fail here closes intraday long-only 5-minute trading on this data; it is not retuned.

## Protocol (unchanged)
- Same data (186-stock liquid universe, cached 5-minute bars), same date split (DEV first 70%, HOLDOUT last 30%, HOLDOUT unexamined).
- A setup reaches HOLDOUT only if DEV mean net return per trade > 0. HOLDOUT runs ONCE per setup; the report is final.
- Eleven setups tried in total (9 + 2): HOLDOUT bootstrap alpha = 0.05 / 11, at least 100 trades and 30 sessions, plus the D6
  concentration limit and the 20 percentage-point drawdown limit.
- Costs: the ASSUMED table (not verified). Reports show gross and net. The owner states costs are his responsibility; the pass test stays on net.
- Long only, closed bars, entry = next bar open, exit = 15:15 bar close, max 5 signals per day, tie-break first trigger time then symbol.

## Setups (version v3)
- R4_HIGHVOL_ORB_LONG: the unchanged ORB_LONG trigger (3-bar opening range, window to 11:30), taken only if (a) the stock's mean
  daily range, (high - low) / close averaged over its previous 20 sessions, is in the top 20% of the universe as of the previous
  session, and (b) the opening-range width (high - low of the first 3 bars) is at least 0.6% of the opening-range low.
- R4_GAP_VOLUME_LONG: the session open is at least 2.0% above the previous session close; the first 3 bars' total volume is at
  least 2.0 x the stock's median first-3-bar volume over the previous 20 sessions; trigger = first bar between 09:30 and 11:00
  whose close is above the high of the first 3 bars. The first 20 sessions of data are excluded.

## Known limits (stated before results)
- Both setups will trade rarely, so one or both may end INCONCLUSIVE rather than pass or fail.
- About 270 sessions is a short history and may cover one regime. Sector concentration and walk-forward are not computed.
- This does not test shorting or other bar sizes; those would be new hypotheses with their own penalty.

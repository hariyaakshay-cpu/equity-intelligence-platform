# Intraday Setups Round 2 - Pre-Registration (written 2026-10-25 BEFORE any round-2 result)

Round 1 (ORB, VWAP reclaim, PDH break; 186 stocks, 269 sessions) failed: mean net -0.18% to -0.25% per trade,
gross about zero. Round 1 is closed and not re-tuned. Parameters below are fixed now and may not change after results.

## Protocol (guards against fitting noise)
- Sessions are split by date: DEV = first 70% of sessions, HOLDOUT = last 30% (never examined until a setup qualifies).
- DEV results are diagnostics only. A setup goes to HOLDOUT only if DEV mean net return per trade > 0.
- HOLDOUT is run ONCE per setup; its result is final (script refuses to overwrite a holdout report).
- Six setups have now been tried in total (3 failed + 3 new), so the holdout needs the 95% bootstrap lower bound
  computed at Bonferroni level alpha = 0.05 / 6 (one-sided-equivalent 99.17% interval) to be above zero,
  plus all D6 thresholds (min trades scaled to the holdout length: at least 100 trades and 30 sessions).
- Same conventions as round 1: long only, closed bars, entry = next bar open, exit = 15:15 bar close, costs as COSTS,
  max 5 signals/day, tie-break first trigger time then symbol.

## Setups (all LONG, version v1)
- GAP_GO_LONG: bar-0 open is 1% to 4% above the previous close; trigger = first bar after the 3-bar opening range
  that closes above the opening-range high, trigger close time <= 10:30.
- DIP_REVERSAL_LONG: at bar index >= 6, close <= session VWAP x 0.985; trigger bar is green (close > open) and closes
  above the previous bar's high; trigger close time <= 13:30. One trigger per session.
- LATE_STRENGTH_LONG: at the bar closing 13:30, close >= previous close x 1.015 and close >= 0.997 x session high so far.
  Trigger is that bar only.

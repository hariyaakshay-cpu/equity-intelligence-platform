# Paper board volume-surge long (live paper test) - pre-registration

Status: FROZEN 2026-11-19 (S1-S6 and R1-R3 approved by Akshay), before any
surge paper trade was recorded. The sha256 of this file is in
`research/paper_board/surge_long_prereg_2026-11-19.sha256`; the board refuses
to score surge trades if it no longer matches (CRLF normalised to LF).
Forward test on live data only. Any change = a new version.

## Where the idea comes from (disclosed)

The live PAPER board (commit 9f49357, latest 253e94a) shows a volume-surge
watchlist. A close cousin was already tested and failed:
R3_VOLUME_SURGE_LONG (round 3 DEV, 5-minute bars, 186 liquid stocks) made 837
trades, mean -0.08% before costs and -0.26% after a 0.18% round trip, 95%
interval -0.46% to -0.07%. The round-4 pre-registration closed further
long-only 5-minute tests on that history, so this rule is judged only on live
data recorded after this file is frozen. Expected result: FAIL.

## Question

Does buying the first few up-on-the-day stocks on the board's surge list and
selling at 15:15 make money after costs? Intraday only (square off the same
day). Paper only; no orders. The owner places any real trade himself.

## Rule (version 1, approved 2026-11-19)

- S1 List: the board's surge list exactly as in
  `equity_intel/paper_board/logic.py` at commit 253e94a: volume so far >= 1.5x
  the stock's 20-session median daily volume times the share of the
  375-minute session elapsed (SURGE_MIN_RATIO = 1.5); 20-session median daily
  traded value >= Rs 10 cr (SURGE_MIN_VALUE_CR = 10.0); nothing before 09:30
  (SURGE_FIRST_MINUTES = 15); top 15 by ratio (SURGE_TOP = 15).
- S2 Trigger and direction: long only. A stock triggers at the first board
  check between 09:30 and 13:00 IST at which it is on the list and up on the
  day (last price > previous close).
- S3 Entry: the last price at the next board check after the trigger (about
  5 minutes later). No check within 15 minutes of the trigger -> VOID.
- S4 Cap: at most 5 trades per session; a VOID trade still uses its slot.
  Trigger checks earliest first; within one check, higher ratio first, then
  symbol A-Z. At most one trade per stock per session.
- S5 Exit: the last price at the first board check at or after 15:15 IST. No
  stop-loss, no target. No check between 15:15 and 15:30 -> exit at that
  session's official close from data/daily_live, marked the next morning.
- S6 Cost: 0.18% round trip (the intraday rounds' assumed cost; not verified,
  costs are the owner's responsibility). Gross % = (exit / entry - 1) x 100;
  net % = gross % - 0.18. Both are reported.

## Review rule (D6, approved 2026-10-24 and 2026-10-25)

- R1 When: judged only once there are >= 300 closed trades and >= 60
  distinct session dates with a closed trade (about mid-February 2027 at the
  earliest). Before that the scorecard is shown, but nothing is decided from
  it. Walk-forward does not apply: every trade is out of sample.
- R2 Pass (all required):
  1. Mean net % per trade > 0.
  2. The two-sided 95% date-block bootstrap interval of the mean net is
     entirely above 0 (10,000 resamples of whole session dates, seed
     20261119).
  3. No single stock above 10% and no sector (NIFTY 500 CSV Industry field)
     above 25% of the summed net %.
  4. Max drawdown <= 20 percentage points: the largest peak-to-trough fall of
     the cumulative sum of net % per trade, summed by date.
- R3 Early stop: if the drawdown in R2.4 passes 20 points at any time, the
  verdict is FAIL at once (it can no longer pass).
- After the verdict: PASS -> still paper, a candidate signal only; any
  real-money use is a separate decision. FAIL -> surge scoring ends; no
  retuning and no variant tested on the same live data.

## Not part of this test

- The order-win fade stays on the board for reference only (failed its
  backtest; about 3-4 trades a month). It has no review.
- The 15-row surge watchlist is unchanged; only the S1-S5 subset is scored.
- Telegram and dashboard wording do not change the rule.

## Known limitations (accepted up front)

- Board checks are about 5 minutes apart and can drift or be missed (the
  laptop may sleep, or the board may start late); S3 and S5 say what happens
  then.
- A quote's last price is not a fill. Spread and slippage are not measured;
  the 0.18% is assumed to cover them.
- The ratio scales the median by clock time, but volume is heavier near the
  open, so the first check after 09:30 flags many stocks. Expect the 5 slots
  to fill at that first check on most days.
- Sector is the NIFTY 500 CSV Industry field (accepted as the v1 sector in B3).

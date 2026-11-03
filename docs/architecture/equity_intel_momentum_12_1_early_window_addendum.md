# 12-1 momentum - early-window replication addendum (written 2026-11-04 BEFORE the early data was fully fetched)

Status: FROZEN with research/momentum/manifest_early_2026-11-04.sha256. At writing, only a 5-symbol smoke fetch
(360ONE, 3MINDIA, AADHARHFC, AARTIIND, AAVAS) existed in data/daily_history_early; no score, return or result from that
window has been computed.

## Purpose
The same rule failed DEV narrowly on 2022-2025 (gross excess +0.30%, net -0.05% per 21 sessions; interval wide). This
tests the IDENTICAL rule on an earlier window none of the equity tests has touched, to get more evidence, not a new rule.

## What is identical (no change of any kind)
Every rule, constant and gate in docs/architecture/equity_intel_momentum_12_1_preregistration.md and the code in
equity_intel/scoring/momentum_12_1.py (hash c71641ae..., unchanged): 252/21 lookback-skip, top 10, 21-session hold,
INR 10 crore liquidity, +/-30% exclusion over t-252..t+21, >= 100 eligible per date, 0.35% cost, equal-weight
benchmark, 95% circular block bootstrap (block 21, 10,000, seed 20261103), >= 100 dates, <= 10% symbol share.

## What differs
- Data: data/daily_history_early (Upstox daily candles 2013-10-01 .. 2021-09-30, fetched 2026-11-04 with
  scripts/equity_daily_history_fetch.py --out-dir), same 490-symbol list plus NIFTY500_INDEX.
- Window: every signal date from the first with >= 100 eligible stocks up to the last whose 21-session exit is on or
  before 2021-09-30. This whole window is ONE test set (no DEV/HOLDOUT split inside it); run once, result never
  overwritten. INR 10 crore is not inflation-adjusted (stated, not changed).

## Decision
- PASS = all four pre-registered gates on this window. A PASS makes the rule eligible for its final check on the
  untouched 2025-09-05 .. 2026-10-28 HOLDOUT (run once), and for paper tracking only. FAIL closes 12-1 momentum.

## Known limits (stated before results)
- Survivorship is WORSE here than in 2022-2026: the list is today's NIFTY 500, so 2014-2021 contains only firms that
  survived and grew into it. This biases momentum results upward. A PASS must be discounted for it; a FAIL is strong.
- Some symbols listed late or have gappy early history (e.g. 360ONE). Gaps are treated as consecutive bars (the
  rule counts bars, not calendar days), as in the original study. Symbol coverage per year will be reported.
- 2014-2021 includes the 2020 crash and rebound; one regime can dominate.

Note: scripts/equity_momentum_12_1.py gained the "early" split on 2026-11-04 (dev/holdout code paths unchanged in behaviour); its new hash is in the early manifest. The 2026-11-03 manifest still describes the code that produced result_dev.json.

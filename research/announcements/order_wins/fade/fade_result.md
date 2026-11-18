# Order-win fade (intraday short) - result (2026-11-18)

Pre-registration: `docs/architecture/order_win_fade_preregistration.md`
(sha256 e5f6c6cd..., checked by the runner). Shares sha256 68b6e9a5... Run once on
Akshay's PC, 2026-11-18 14:37 IST, with the runner exactly as reviewed (runner
files last modified 14:35 IST; committed together with this result).

## Frozen verdict: FAIL (rule 4, concentration)

| Rule | Required | Result | |
|---|---|---|---|
| 1. trades / sessions | >= 100 / >= 40 | 166 / 154 | pass |
| 2. mean net short abnormal | > 0 | +0.508% | pass |
| 2. mean net short raw | > 0 | +0.543% | pass |
| 3. one-sided 95% lower bound | > 0 | +0.155% | pass |
| 4. max symbol share of profit | <= 10% | 55.2% (KEC) | **FAIL** |

59 symbols; win rate 61.4% after costs; 6 units dropped as non-EQ series;
no locked-low entries; no moves above 20%.

KEC International: 26 of 166 trades, 55% of the summed net short abnormal
return; BLKASHYAP a further 21%; 22 symbols lost money on balance.

## Diagnostics (exploratory, same data, do not change the verdict)

- Without KEC: n 140, mean +0.27%, lower bound -0.13% (not significant).
- Without KEC and BLKASHYAP: n 133, mean +0.15%, lower bound -0.24%.
- By entry year (mean net short abnormal): 2023 +0.69% (60), 2024 +0.38%
  (35), 2025 +1.27% (29), 2026 -0.17% (42).

The headline profit rests mainly on one frequent filer, and the 2026 trades
were negative. Rule 4 did what it was written for.

## Decision

Per D7: the fade is CLOSED as FAIL. No re-run, no change to threshold,
horizon, cost or concentration rule, and no "ex-KEC" variant (that would be
choosing the sample after seeing it). With v1 (categories), v2.1 (long) and
this fade all failed, the order-win line of research ends here.

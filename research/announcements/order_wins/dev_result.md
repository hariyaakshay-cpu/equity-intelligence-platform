# Order-win event study v2.1 - DEV result (2026-11-18)

Pre-registration: `docs/architecture/order_win_event_study_preregistration_v2_1.md`
(sha256 8d9c9697..., checked by the runner). Shares: `shares_mcap17112026/shares.csv`
(sha256 68b6e9a5..., from mcap17112026.csv). Run once on Akshay's PC with the
unchanged runner, 2026-11-18 14:21 IST. HOLDOUT (2023-2026) NOT run or looked at.

Inputs: 2,518 order wins -> 1,594 units (354 symbols, 293 with prices).
Drops: overlap 606, illiquid 568, no price file 177 (delisted/merged), locked
entry 9, no entry session 4, missing rows / exit sessions 14.

## Frozen verdict: FAIL (0 of 3 PRIMARY horizons pass)

| PRIMARY (>= 5% of mcap) | n | sessions | mean net abnormal | mean net raw | lower bound | verdict |
|---|---|---|---|---|---|---|
| H0 (same-day close) | 309 | 286 | -1.28% | -1.43% | -1.65% | FAIL |
| H5 | 308 | 285 | -1.79% | -1.68% | -2.68% | FAIL |
| H20 | 308 | 285 | -2.16% | -1.02% | -3.72% | FAIL |

Every secondary threshold (>= 2%, >= 10%, all sizes) is negative at every
horizon too. Before the 0.50% cost, H0 is still about -0.78% vs the
equal-weight liquid basket: buying at the open after a big order win lost
money on average even with zero costs. `max_symbol_share` is blank because the
summed return is negative (rule 4 is not reached; rule 2 already fails).

Survivorship note: the 61 delisted/merged symbols that dropped out would, if
anything, have made results worse, so the bias does not rescue the verdict.

## Decision

Order-win v2.1 is CLOSED as FAIL. Per the pre-registration, HOLDOUT is only
run for horizons that pass DEV, so it is not run; 2023-2026 stays unseen.
No re-run or re-tuning of v2.1.

Exploratory observation only (not tested, not a signal): the H0 loss means
these stocks tended to fall from the open to the close on the entry day after
the news. Any idea built on that needs its own new pre-registration, tested
on 2023-2026 data that no study has used yet.

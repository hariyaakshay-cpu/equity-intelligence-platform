# 12-1 momentum, DEV result (2026-11-03): FAIL (narrowly). HOLDOUT NOT RUN.

Frozen before results at commit 1626227 (manifest research/momentum/manifest_2026-11-03.sha256).
DEV: 702 signal dates, 2022-10-07 .. 2025-08-04, top 10 by 12-1 return, 21-session hold, 0.35% assumed round trip.

| Measure | Value |
|---|---|
| Gross return per cohort | +2.55% |
| Net return per cohort | +2.20% |
| Equal-weight liquid market, same window | +2.25% |
| Net excess (decision measure) | -0.05% |
| Gross excess (before costs) | +0.30% |
| Net excess vs NIFTY 500 index (secondary) | +1.04% |
| 95% block-bootstrap interval of net excess | [-1.63%, +1.53%] |
| Dates with positive excess | 52% |
| Picks dropped by the +/-30% corporate-action rule | 191 |

Reading: unlike scoring v0, momentum picks beat the average liquid stock BEFORE costs (+0.30% per 21 days), but the
pre-registered 0.35% cost (which assumes 100% turnover every cohort) removes all of it. The interval is wide: the
data can neither show an edge nor rule one out. Per the pre-registration this hypothesis is closed on this data and not
retuned (no change of turnover assumption, lookback, size or hold after seeing this). HOLDOUT remains unread.

Headline recomputed with independent code directly from data/daily_history: 702 dates, -0.0484%, identical.

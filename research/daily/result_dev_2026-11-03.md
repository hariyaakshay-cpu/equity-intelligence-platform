# Daily study, DEV result (2026-11-03): BOTH LISTS FAIL. HOLDOUT NOT RUN.

Frozen before results at commit 09687b2 (manifest research/daily/manifest_2026-11-03.sha256, all 13 hashes verified).
DEV = 704 signal dates (first 70%, Oct 2022 onward after 252-bar warm-up), 490 symbols, cost 0.35% round trip.

| List | Hold | Dates | Net return / trade | Equal-wt market | Net excess | Gross excess (pre-cost) | 97.5% block-bootstrap |
|---|---|---|---|---|---|---|---|
| Short (momentum+volume+breakout) | 5d | 695 | -0.23% | +0.36% | -0.59% | -0.24% | [-0.88%, -0.31%] |
| Medium (trend+RS+52w distance) | 20d | 704 | +1.40% | +2.13% | -0.73% | -0.38% | [-1.47%, -0.01%] |

Both lists underperform an equal-weight basket of all liquid NIFTY 500 stocks, before and after costs. The medium
list beats the cap-weighted NIFTY 500 index by +0.30% per 20 days (secondary, not a gate), which only says that the
average liquid stock beat the index in this period (and survivorship flatters all of it).

Headline numbers recomputed with separate code from replay_dev.csv: identical to 4 decimals.

Per protocol this version (scoring v0 provisional bands, top-10, cutoff 70, H = 5/20) is CLOSED and is not retuned on
this data. HOLDOUT (283 dates) was never read.

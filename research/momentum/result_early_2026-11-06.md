# 12-1 momentum, early-window replication (2014-2021): FAIL. Momentum closed. HOLDOUT NOT RUN.

Frozen before data at commit 54e6778 (addendum + research/momentum/manifest_early_2026-11-04.sha256; all six
hashes re-verified OK before the run). Data: data/daily_history_early, Upstox daily 2013-10-01..2021-09-30,
491 files, symbols with data per year 304 (2013) .. 403 (2021); 81 symbols listed after 2021 have no rows.

| Gate (pre-registered) | Result | Pass |
|---|---|---|
| Mean net excess > 0 | +0.88% per 21 sessions (gross +1.23%) | yes |
| 95% block-bootstrap lower bound > 0 | [+0.06%, +1.74%] | yes |
| >= 100 signal dates | 1,698 (2014-10-14 .. 2021-08-31) | yes |
| No symbol > 10% of total excess | ADANIGREEN 30.4% | NO |

Verdict: FAIL. Per the addendum, a FAIL closes 12-1 momentum; the 2025-09-05..2026-10-28 HOLDOUT stays unread.

Diagnostics (computed after the verdict; they do not change it):
- Independent recomputation from the raw CSVs: 1,698 dates, +0.8804%, ADANIGREEN share 0.304 (identical).
- Top five symbols' shares of total excess: ADANIGREEN 30.4%, HEGAM 28.8%, GRAPHITE 17.9%, DIXON 15.1%,
  ESCORTS 12.9% = about 105%. The rest of the universe together contributed slightly below zero.
- Without ADANIGREEN: +0.66%, and HEGAM becomes 38% of the total. The concentration is structural, not one outlier.
- Net excess by signal year: 2014 +3.19, 2015 -0.24, 2016 -1.01, 2017 +2.97, 2018 -0.88, 2019 +1.45,
  2020 +1.38, 2021 +2.54 (% per 21 sessions). Three of eight years negative.
- The universe is today's NIFTY 500, so 2014-2021 contains only firms that survived and grew into it. The few
  multi-baggers that carry the result are exactly the names survivorship selects (stated as the main limit before
  the run).

Reading: on this data the rule's average edge comes from a handful of extreme winners known only with hindsight
to be in today's index, not from the broad list. That is not a tradeable edge to rely on. Max drawdown of the
summed overlapping-cohort curve (464 points) is reported by the evaluator but is not a meaningful size measure.

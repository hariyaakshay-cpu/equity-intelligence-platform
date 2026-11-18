# Announcement event study v1 - DEV result (2026-11-08)

Pre-registration: `docs/architecture/announcement_event_study_preregistration.md`
(sha256 3140c83b..., verified before the run). Data:
`research/announcements/coverage_20261108T012112/` (1,521 weekdays
2021-01-01 to 2026-10-30, all HTTP 200, 847,679 announcements, 100% with
dissemination time). HOLDOUT (2025-2026) has NOT been run or looked at.

Execution note: observations were built in 4 symbol chunks with the module's
`build_observations` (the device shell caps a call at 180 s), then
`eligible_categories` / `evaluate` exactly as the runner's dev branch.
Units are per symbol, so this equals one pass. Details in `dev_meta.json`.

## Frozen verdict

- 486 symbols with prices; 441,376 DEV observations; 43 eligible categories;
  K = 129 tests; multiple-testing confidence 1 - 0.05/129.
- **1 PASS: "Trading Window", H5** - n 4,314, 440 entry sessions, mean net
  abnormal +0.551%, lower bound +0.104%, max symbol share 3.9%.
- 128 FAIL. Most categories are negative after costs at every horizon,
  including the information-bearing ones: Financial Result Updates
  (H0 -0.48%, H1 -0.61%, H5 -0.52%), Outcome of Board Meeting (H0 -0.42%),
  Credit Rating, Acquisition, Dividend. Buying at the next open after the news
  is public did not pay.
- One H5 observation recomputed by hand from the CSVs (GPIL 2023-07-03 ->
  2023-07-10) matched the module exactly.

## Diagnostic on the one pass (exploratory, DEV only, does not change the verdict)

"Trading Window" filings are the routine insider blackout notices every
company files at quarter end: entries cluster on the last days of Mar/Jun/
Sep/Dec and the first days of the next month (up to 124 stocks on one day).

Same trades measured against the equal-weight average of all liquid universe
stocks (same INR 10 cr rule) over the identical entry-open -> exit-close days:

| | 2021 | 2022 | 2023 | 2024 | All |
|---|---|---|---|---|---|
| net vs NIFTY 500 (frozen metric) | +1.06% | +0.71% | +0.34% | +0.40% | +0.55% |
| net vs equal-weight liquid universe | +0.16% | -0.34% | -0.24% | -0.42% | **-0.22%** |

The pass is explained by a turn-of-quarter rally in the broad (mid/small-cap
heavy) universe relative to the cap-weighted index, not by the announcement.
The session bootstrap also overstates certainty here: ~16 quarter turns drive
the result, and 5-day windows of adjacent sessions overlap.

## Conclusion

v1 finds **no announcement-type edge** for next-open entries on NSE's own
categories. Recommendation: do not run v1 HOLDOUT on this pair, so 2025-2026
stays unseen for any separately pre-registered follow-up (for example a
turn-of-quarter equal-weight test, or v2 with content-based categories and
same-day intraday entries for in-hours events). Decision pending with Akshay.

## Decision (2026-11-18)

v1 is CLOSED as FAIL. The single DEV pass ("Trading Window", H5) is a
turn-of-quarter size effect, not an announcement effect (-0.22% net vs the
equal-weight liquid universe). The v1 HOLDOUT is NOT run, so 2025-2026 stays
unseen for separately pre-registered follow-ups (order-win v2 first). v1 is
not re-run or re-tuned.

`dev_observations.csv` (75 MB) is kept on disk but not committed; its inputs
are pinned by `raw_manifest_sha256` and `prereg_sha256` in `dev_meta.json`.

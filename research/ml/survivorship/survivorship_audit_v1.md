# Survivorship audit v1 (ML spec 5A.2)

RESEARCH ONLY — NOT A TRADING RECOMMENDATION. Built 2026-10-05T18:25:30+00:00.

## Result

- **Membership reconstruction: PARTIAL: drift stored per date, no cutoff applied; reviewer to choose.** Membership is rebuilt backwards from the snapshot using NSE Indices press releases. The reconstructed set size minus the snapshot size (drift) is stored for every date (`survivorship_drift_by_date.csv`) and summarised by year below. No cutoff date is asserted.
- **Candidate samples** (current constituent × session, 2011-01-03 to 2026-09-29): 238,793. **15.68%** use a name the reconstruction says was not in the index at the time and **0.08%** have an unresolved membership chain. Read each year's share together with that year's drift.
- **The stored one-year window** (2025-09-23 to 2026-09-29): 6.39% of samples are reconstructed non-members (a name used before it entered the index).
- A dataset on today's constituents keeps the label `universe: current constituents — NOT point-in-time` unless the reviewer approves a drift bound. This audit measures the bias; it does not remove it.

## Inputs

| Input | sha256 |
|---|---|
| snapshot_sha256 | `df2afcde5e85bf24e098311b898b3245e81525cca02fb0a8b38dd0ebb40077d4` |
| events_sha256 | `de7bf6b30d53e545985889d52623f1120790e02669aaecb17eae24d4a2622b1c` |
| aliases_sha256 | `d1c16c2e7c0a14f21d1bcd2acfc7d9cbbe6a67a4ccb22effedb2157a90aca988` |
| calendar_sha256 | `7babff066e13c8137d10fbabb03246d95b8779b0363affe6287e4ddd1d183e72` |
| vendor_first_bars_sha256 | `b5d1d3f8652051f26507f08cedc0ead637d0b55ae00b2193ec78a901ac8497a4` |
| press_release_fetch_log_sha256 | `5e092be877f4a100b0d21c081e106fd6804b3605a3255fbe9a91ea29cb6f79d1` |

Press releases come from niftyindices.com (`sources/press_releases/`); `sources/fetch_log.json` lists every file with its hash. The snapshot has 501 rows as of 2026-09-24 (one is HFCL, series BE).

## Item 1 — entrants inside the window

Current constituents whose first Upstox bar is after 2011-01-03: **40** of 90 audited. By year of first bar:

| Year | Entrants |
|---|---|
| 2011 | 2 |
| 2015 | 3 |
| 2016 | 2 |
| 2017 | 3 |
| 2018 | 3 |
| 2019 | 1 |
| 2020 | 1 |
| 2021 | 6 |
| 2023 | 6 |
| 2024 | 5 |
| 2025 | 8 |

Inside the stored window (first bar after 2025-09-23): **3**.

## Item 2 — membership evidence

Symbols that are not reconstructed as full-period members without an anomaly: 12 of 90 over the stored window; 51 over the full calendar span. Per-symbol counts: `survivorship_by_symbol.csv`.

## Item 3 — candidate samples by class, with drift

| Year | Member | Not a member | Uncertain chain | Samples | Not a member, % | Mean drift | Max abs drift |
|---|---|---|---|---|---|---|---|
| 2011 | 9,973 | 2,513 | 0 | 12,486 | 20.13 | 28.45 | 30 |
| 2012 | 10,291 | 2,761 | 0 | 13,052 | 21.15 | 25.19 | 26 |
| 2013 | 10,250 | 2,750 | 0 | 13,000 | 21.15 | 24.22 | 25 |
| 2014 | 10,004 | 2,684 | 0 | 12,688 | 21.15 | 23.91 | 24 |
| 2015 | 10,296 | 2,794 | 0 | 13,090 | 21.34 | 22.74 | 23 |
| 2016 | 11,119 | 2,714 | 0 | 13,833 | 19.62 | 19.23 | 22 |
| 2017 | 11,889 | 2,537 | 0 | 14,426 | 17.59 | 13.73 | 17 |
| 2018 | 12,647 | 2,510 | 0 | 15,157 | 16.56 | 10.09 | 12 |
| 2019 | 13,411 | 2,131 | 63 | 15,605 | 13.66 | 8.31 | 9 |
| 2020 | 13,467 | 2,775 | 120 | 16,362 | 16.96 | 4.8 | 7 |
| 2021 | 13,772 | 2,977 | 0 | 16,749 | 17.77 | 1.0 | 1 |
| 2022 | 15,014 | 2,594 | 0 | 17,608 | 14.73 | 1.76 | 2 |
| 2023 | 15,745 | 2,126 | 0 | 17,871 | 11.9 | 1.25 | 2 |
| 2024 | 17,808 | 1,650 | 0 | 19,458 | 8.48 | 1.0 | 1 |
| 2025 | 19,429 | 1,667 | 0 | 21,096 | 7.9 | 0.75 | 1 |
| 2026 | 6,045 | 267 | 0 | 6,312 | 4.23 | 0.0 | 0 |

Drift is in names; positive means the rebuilt set is larger than the snapshot.

## Names in the index that are not in today's universe

The other side of survivorship: reconstructed members at a date that are absent from the 2026-09-24 list (sampled about monthly; an undercount wherever an exit was not found).

| Year | Mean members | Mean not in universe | Share, % |
|---|---|---|---|
| 2011 | 529.5 | 270.3 | 51.05 |
| 2012 | 526.2 | 266.2 | 50.59 |
| 2013 | 525.2 | 265.2 | 50.5 |
| 2014 | 524.9 | 264.9 | 50.47 |
| 2015 | 523.8 | 263.1 | 50.23 |
| 2016 | 520.5 | 249.7 | 47.98 |
| 2017 | 515.0 | 232.2 | 45.09 |
| 2018 | 511.2 | 213.9 | 41.85 |
| 2019 | 509.3 | 190.3 | 37.37 |
| 2020 | 505.9 | 177.7 | 35.12 |
| 2021 | 502.0 | 165.5 | 32.98 |
| 2022 | 502.8 | 147.8 | 29.39 |
| 2023 | 502.3 | 127.8 | 25.45 |
| 2024 | 502.0 | 95.0 | 18.92 |
| 2025 | 501.8 | 52.0 | 10.36 |
| 2026 | 501.0 | 10.7 | 2.13 |

## Cross-check: index entry before the first bar

A reconstructed entry date earlier than the stock's first Upstox bar is impossible unless the name is a demerger spin-off included under a dummy symbol. Entries that fail: **0**.

## Item 4 — reconstructability

**PARTIAL: drift stored per date, no cutoff applied; reviewer to choose.** `parse_press_releases.py` reads the Nifty 500 section of each press release; `reconstruct_membership.py` undoes the changes backwards from the snapshot and checks each change against the set (`membership_anomalies.csv`). 1470 change rows were read, 3 revocations applied, 53 checks failed overall, 8 of them on current constituents. Snapshot size: 501; drift by date is stored.

**Does the vendor still serve names that left the index?** From the symbols that left the index from 2020-03-27 on, are not in the snapshot and resolve by trading symbol in the local Upstox master, 30 were sampled (deterministic, `vendor_sample90.py`). 30 returned bars; 30 of those stop before 2026-09-01. 51 such symbols do not resolve in the master at all (renamed, merged or delisted) and could not be sampled. Resolution is by symbol only (ISIN not verified). Sample fetch: 258 calls, stopped: complete.

## Limits

- Older years drift more: releases for 2011-2019 exist, but the rebuilt set grows past the snapshot size and some changes conflict. No cutoff is applied here.
- Renamed symbols are mapped by company-name continuity (`symbol_aliases.csv`, status INFERRED). That is inferred, not documentary.
- Inclusions with no found exit (for example AKZOINDIA, MFL, MAHINDCIE) leave those names out of the rebuilt set between entry and an unknown exit. They are not current constituents, so the sample classes are unaffected; the 'not in universe' table undercounts.
- Temporary index entries for demerged companies (dummy symbols) and the 'Exclusion of ...' releases are saved but not modelled. They last days to weeks.
- The deferred March 2020 rebalancing is handled by `void_events.csv`, citing the 13 May 2020 release.
- Candidate samples assume a bar on every session between a symbol's first and last bar. Holes belong to the data-quality audit.
- Any drift bound that decides which dates count as usable must be chosen and approved by the reviewer before a dataset relies on it.

## Reproduce

```
python research/ml/survivorship/fetch_sources.py
python research/ml/survivorship/parse_press_releases.py
python research/ml/survivorship/reconstruct_membership.py
# from the repository root that holds .env and data/:
python research/ml/survivorship/vendor_first_bars.py
python research/ml/survivorship/vendor_first_bars.py --removed
python research/ml/survivorship/build_audit.py
```

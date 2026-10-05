# Upstox daily-candle adjustment basis: split/bonus check (2026-10-03)

Branch run on: `equity-intel/adjustment-check` (HEAD 3bac136). Tool: `scripts/check_adjustment_basis.py`
(read-only; writes no DB row, snapshot or ScanRun; saves the instrument master under `data/reference/`).

## Question

Are Upstox daily candles, as fetched through the scanner's `fetch_symbol_candles`, adjusted for
splits and bonuses? Observed ratio = close on/after ex-date / close before. Near 1.0 means adjusted;
near 1/divisor means raw.

## Result

All four runs: single-day gap between the two sessions, ratio near 1.0, far from 1/divisor.

| Symbol | Ex-date | Divisor | Before | On/after | Ratio | Dist. to 1.0 | Dist. to 1/divisor |
|---|---|---|---|---|---|---|---|
| MCX | 2026-01-02 | 5 | 2026-01-01 / 2198.0 | 2026-01-02 / 2216.0 | 1.0082 | 0.0082 | 0.8082 |
| KOTAKBANK | 2026-01-14 | 5 | 2026-01-13 / 426.5 | 2026-01-14 / 421.0 | 0.9871 | 0.0129 | 0.7871 |
| BSE | 2025-05-23 | 3 | 2025-05-22 / 2332.0 | 2025-05-23 / 2448.0 | 1.0497 | 0.0497 | 0.7164 |
| BRIGADE | 2026-06-17 | 1.3333 | 2026-06-16 / 540.2 | 2026-06-17 / 565.85 | 1.0475 | 0.0475 | 0.2975 |

No run was INCONCLUSIVE and none returned a 401. No pair of sessions was more than 4 calendar days apart.

## NSE verification

The ex-dates and ratios used above came from news pages. They were later checked against NSE's own
corporate-actions data (NSE `corporates-corporateActions` endpoint, queried from a browser session on nseindia.com,
per symbol, filtered to split/bonus-type subjects, on 2026-10-03):

| Symbol | NSE ex-date | NSE subject | Implied divisor | Used | Match |
|---|---|---|---|---|---|
| MCX | 02-Jan-2026 | Face Value Split, Rs 10 to Rs 2 | 5 | 5 | yes |
| KOTAKBANK | 14-Jan-2026 | Face Value Split, Rs 5 to Re 1 | 5 | 5 | yes |
| BSE | 23-May-2025 | Bonus 2:1 | 3 | 3 | yes |
| BRIGADE | 17-Jun-2026 | Bonus 1:3 | 4/3 | 1.3333 | yes |

- The bonus divisors rest on reading "Bonus a:b" as a new shares per b held, giving (a+b)/b. NSE's data does not
  state this convention; it is an interpretation.
- Older actions returned by the same query (KOTAKBANK 2015 bonus and 2010 split, BSE 2022 bonus, BRIGADE 2019 bonus)
  fall outside every checked window. Other action types were filtered out, not reviewed.
- Consequence: the "wrong ex-date on a raw series" explanation for a near-1.0 ratio is ruled out for all four.

## Evidence strength per case

- **MCX, KOTAKBANK:** full close series for ex-date +/-10 calendar days was printed (13 sessions each).
  Day-over-day ratios range 0.9679-1.0263 (MCX) and 0.9797-1.0208 (KOTAKBANK). No ~0.2 drop anywhere in either window,
  so a raw series is ruled out for the window. The ex-date itself is confirmed by NSE (above).
- **BSE:** reported (by a reviewer, not re-derived in this session) that the article's unadjusted pre-event close of
  6,996.5 / 3 = 2,332.2 matches the fetched 2,332.0 on 2025-05-22. If correct, this independently shows the
  divided-down price is what Upstox returns.
- **BRIGADE:** full close series for ex-date +/-10 calendar days was printed (14 sessions, 2026-06-08 to 2026-06-25).
  Day-over-day ratios range 0.9662-1.0528; 2026-06-17 is 1.0475 (neighbours 1.0528 on 06-16, 0.9801 on 06-18).
  No ~0.75 step anywhere, so a raw series is ruled out for the window. Price rose ~17% over the window
  (482.35 to a high of 565.85 on 06-17) in mostly 4-5% daily steps: real movement, not an adjustment artifact.
  The ex-date itself is confirmed by NSE (above).

## Not verified

- Nothing about the four events remains unverified (see "NSE verification" above). Four events is a small sample. Demergers are not covered by this check; the earlier finding that they
  are not adjusted stands. Splits/bonuses only.

## Caveat: "adjusted" means adjusted at fetch time

- E4 reads prices from one acquisition run (`equity_intel/features/runner.py:75-77`, `acquired_observations`
  filtered by `run_id`), not from `price_fetch_snapshots`. Each run fetches its own window
  (`CALENDAR_LOOKBACK_DAYS = 500`), so history within a run shares one adjustment basis.
- `price_fetch_snapshots` is append-only (`equity_intel/scanner/snapshots.py:114`). A run stored before an ex-date
  keeps raw prices; re-running E4 on that stored run is not flagged. Not tested end to end.
- `equity_intel/acquisition/backfill.py:22-41` appends only bars strictly newer than the newest held bar, from a
  14-day refetch in the same run. It cannot mix with earlier runs; a basis mix would need an ex-date to take effect
  between two fetches seconds apart (negligible).
- `equity_intel/features/breaks.py:19-28` flags close-to-close ratios outside low/high thresholds (flag only, never
  adjusts) and is the backstop for any mixed-basis split. It does not detect demergers with ratio near 1.
- Minor, unrelated to adjustment: `backfill._bar_date` uses `stamp.date()` without IST conversion
  (`backfill.py:15-19`); provider timestamp timezone not checked.

## Side effects of the runs

- Tracked files: none changed (`git status --short` and `git diff --stat` empty after the runs).
- New file `data/reference/upstox_NSE_instruments_2026-10-03_c586af63.json.gz` (~1.9 MB), gitignored by
  `.gitignore:11` (`data/reference/*.json.gz`). Snapshots accumulate per run; prune occasionally.
- Full suite at the time: 415 passed, 1 skipped (`equity_intel/tests/test_db_path_guard.py:60`, symlink creation
  not permitted in this environment).

## Suggested follow-ups

1. Decide how to treat E4 runs stored before a later ex-date.

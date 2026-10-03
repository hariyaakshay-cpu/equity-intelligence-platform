# Equity Intelligence Platform

A data-only research pipeline over the Nifty 500: it acquires daily candles from Upstox, validates them, and
computes raw indicator features that a read-only dashboard displays. It does **not** score, rank, recommend or trade.
B2 scoring is blocked, and importing broker/execution modules is refused at runtime and by static tests.

## Stages

| Stage | What it does | Entry point |
|---|---|---|
| E1-E3 acquisition | Nifty 500 universe, ISIN to Upstox key mapping, daily candles and the `NSE_INDEX\|Nifty 500` benchmark, validation, stored per `run_id` | `scripts/equity_data_acquisition.py` |
| E4 features | Reads one stored acquisition run (no vendor calls): break detection, EMAs, RSI, ROC, relative return, relative volume, ATR, distance from high; per-symbol `VALID` / `INSUFFICIENT_HISTORY` / `STALE` / `FAILED` | `scripts/equity_e4_scan.py` |
| Scanner v1 | Separate pipeline with immutable price snapshots and symbol classification | `python main.py scan` / `scripts/equity_scan.py` |
| Dashboard | Read-only Flask view of stored results | `python main.py dashboard [--demo]` |

All results live in one SQLite file, `data/equity_intel.db`, opened only through the path guard
(`equity_intel/persistence/db_path_guard.py`). The database and fetched files under `data/` are git-ignored.

## Running

```
pip install -r requirements.txt
python scripts/upstox_auth.py            # Upstox token expires daily (~03:30 IST); writes UPSTOX_ACCESS_TOKEN to .env
python scripts/equity_data_acquisition.py
python scripts/equity_e4_scan.py
python -m pytest equity_intel tests
```

Indicator parameters are in `config/indicators_v1.json` (labelled provisional).

## Data-correctness rules to know

- **Calendar is provisional.** The benchmark dates returned in the same acquisition run are the v1 calendar. No official NSE
  calendar is claimed (`calendar_status = PROVISIONAL`). See `research/b3_07_v1_provisional_calendar_decision_2026-10-03.md`.
- **Dates are IST.** Candle timestamps are converted to IST before taking the date (`equity_intel.config.session_date`).
- **Adjusted at fetch time.** Upstox adjusts splits and bonuses when you fetch, so a stored run keeps the basis of its fetch day
  (`research/upstox_adjustment_basis_check_2026-10-03.md`). If `data/reference/corporate_action_review.csv` lists an action
  effective on or after a run's IST fetch date, E4 marks that symbol `STALE` with reason `ADJUSTMENT_BASIS_STALE` and withholds
  its features. Clear it by running a fresh acquisition, then E4 again. Stored rows are never edited, and each E4 scan records the
  review file's hash.
- **Demergers are not adjusted** and are not detected when the price ratio is near 1; see `docs/architecture/equity_demerger_handling.md`.
- Breaks (close-to-close ratio below 0.5 or above 2.0) are flagged and history is truncated there. Nothing is adjusted.

## Layout

`equity_intel/` (acquisition, features, scanner, persistence, contracts, tests) · `core/providers/` (Upstox client) ·
`dashboard/` · `scripts/` · `config/` · `data/reference/` (inputs) · `docs/architecture/` (design and spec) ·
`research/` (dated evidence and decision notes).

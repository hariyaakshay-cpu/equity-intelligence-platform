# Equity Intelligence E1-E3 Data Acquisition

Status: **implemented research/data pipeline; not a production scanner and not a trader**.

The pipeline loads the committed 2026-09-24 NIFTY 500 constituents CSV,
excludes `DUMMY*` placeholders with an explicit report entry, joins the
remaining constituents to the local Upstox NSE instrument master by ISIN
(exact symbol fallback only if ISIN has no match), fetches daily candles,
validates them, and stores exactly the latest 252 returned observations
for symbols that pass validation and history requirements.

## Run

Set `UPSTOX_ACCESS_TOKEN` through the existing `.env` / environment settings
and run from the repository root:

```powershell
python scripts/equity_data_acquisition.py
```

Optional `--start-date` and `--end-date` arguments use ISO dates. The default
request range is 500 calendar days ending on the current India date; the
pipeline counts actual returned observations and never infers session count
from calendar days. The Upstox instrument master is a local input and is not
committed; the default file path is ignored by Git. Missing token or input
files produce a clear configuration/input error.

Each run creates `data/equity_intel.db` and JSON/Markdown reports under
`data/equity_intel/reports/`. Database writes pass through the existing
canonical-path guard. Same-run observation uniqueness is
`(run_id, symbol, trading_date, source_vendor)` with `INSERT OR REPLACE`.
Run summaries include input SHA-256 values, requested dates, per-symbol
states, validation details, counts, source, retrieval time, instrument key,
adjustment note, and calendar label.

## Boundaries and current limitations

- `calendar_status` is **PROVISIONAL**. Returned Upstox observation dates
  define each acquired series; no official NSE session calendar is claimed.
  B3-07 remains open.
- Upstox daily history is split-adjusted according to the recorded evidence;
  demerger adjustments are not made. This pipeline validates observed values
  and does not repair them.
- Symbols with fewer than 252 returned observations are marked
  `INSUFFICIENT_HISTORY` and are not persisted as a 252-session dataset.
- Zero volume is retained and explicitly reported as a warning; negative or
  missing volume invalidates an observation set.
- API failures are isolated per symbol. The provider retries transport
  failures and HTTP 429/5xx at most three total attempts; permanent 4xx
  responses fail immediately. HTTP 401 aborts the run and later symbols are
  marked `NOT_REQUESTED`. Requests are paced at five per second.
- Live vendor access and a complete 500-symbol run were not exercised by the
  test suite. The pipeline needs a valid local token and current master file
  to produce actual run data.
- E1-E3 does not calculate indicators or scores. E4 is the next separate
  scope gate. No rank, recommendation, watchlist, OMS, order, or trading
  integration is present.

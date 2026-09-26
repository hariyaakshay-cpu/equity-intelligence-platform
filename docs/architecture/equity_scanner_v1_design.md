# Equity Scanner v1 — Design (data-only, no scoring)

Status: DESIGN DRAFT. Non-functional design only; nothing in this document
authorizes a threshold, a scoring rule, or a candidate/watchlist decision.
B2 remains BLOCKED (`docs/architecture/equity_intel_boundary_decision.md`);
this design does not touch scoring, classification, candidate selection, or
the watchlist in any way.

## 0. Scope, as fixed by Akshay

- Universe from `data/reference/nifty500_constituents_*.csv`; exclude
  `DUMMY*` rows; flag non-`EQ` `Series` values (e.g. `BE`).
- ISIN → `NSE_EQ` `instrument_key` mapping from the Upstox instrument
  master; benchmark is `NSE_INDEX|Nifty 500`.
- Daily candles, full re-fetch of the window every run (never append —
  design rule 4a, `research/b3_live_evidence_resolution_2026-09-26.md`
  Section 4a).
- Per-stock data-quality checks: session count vs. requirement,
  zero-volume days, date alignment with the benchmark, and a
  corporate-action break detector (flag, don't adjust — design rule 4b,
  same file, Section 4b).
- Indicators from `equity_intel/indicators/` only. No scoring, candidates,
  or watchlist (B2 blocked).
- Persistence only through a new `persistence/connection.py` that calls
  `db_path_guard` first; scan states per the existing contracts; the
  dashboard later reads only `COMPLETE` scans.
- Entry point `scripts/equity_scan.py`, calling the forbidden-module guard
  at start.

## 1. Pipeline shape

`equity_intel/scanner/shell.py:1-10` already declares this stage order and
`equity_intel/scanner/shell.py:57-69` (`ScanPipeline.run`) already calls
`assert_no_forbidden_modules_loaded()` (line 58) before any stage runs.
This design fills in the first four stages only — `_load_universe`,
`_load_market_data`, `_validate_data`, `_compute_features`
(`shell.py:71-91`) — and stops there. `_score` and everything after it
(`shell.py:93-113`) stay exactly as they are: `NotImplementedError`,
naming the B2 blocker. This design proposes no change to `shell.py`'s
`_score`/`_classify`/`_select_candidates`/`_persist_watchlist` bodies.

```
load universe (CSV, filtered)
    -> map to instrument_key (ISIN join)
    -> fetch benchmark candles (full window)
    -> for each instrument:
         fetch candles (full window, re-fetch not append)
         -> data-quality checks (incl. corporate-action break detector)
         -> compute features (equity_intel/indicators/)
    -> persist per-instrument FeatureSet + DataQualityResult
    -> record scan_run status
```

## 2. Universe loading

Source: `data/reference/nifty500_constituents_*.csv`, columns confirmed in
`research/b3_live_evidence_resolution_2026-09-26.md` Section 2 (`Company
Name, Industry, Symbol, Series, ISIN Code`; 501 rows in the 2026-09-24
file). Maps to `equity_intel.contracts.market_data.InstrumentMember`
(`equity_intel/contracts/market_data.py:35-53`): `symbol` from `Symbol`,
`company_name` from `Company Name`, `sector` from `Industry` (per B3-04's
MET-for-v1 verdict — a free-form string per
`equity_intel/contracts/market_data.py:41-43`'s own docstring, not a
constrained taxonomy), `isin` from `ISIN Code`.

Row filtering, per the design rules recorded in
`research/b3_live_evidence_resolution_2026-09-26.md` Section 4(c):
- Exclude any row whose `Symbol` matches `DUMMY*` (the evidence file
  documents exactly one such row, `DUMMYHEG`, tied to the HEG demerger).
- Flag (not exclude) any row whose `Series` is not `EQ` (the evidence file
  documents exactly one such row, `HFCL`, `Series=BE`) — `BE` is a
  trade-for-trade series with no intraday trading, which the scanner
  should be able to distinguish from a data problem.

Where this filtering logic lives, and the exact resulting `active`/status
representation on `InstrumentMember`, is not fixed by this design — see
Open Questions.

## 3. Instrument mapping

By ISIN, against the `NSE_EQ`-segment records in the Upstox instrument
master, exactly as validated in Step 2 of
`research/b3_live_evidence_resolution_2026-09-26.md` (500/500 unique
one-to-one matches once `DUMMYHEG` is excluded). Result populates
`InstrumentMember.instrument_key` (`equity_intel/contracts/market_data.py:49`).

Benchmark: `NSE_INDEX|Nifty 500` (verdict B3-03,
`research/b3_live_evidence_resolution_2026-09-26.md` Section 3), mapped to
`equity_intel.contracts.market_data.BenchmarkObservation`
(`equity_intel/contracts/market_data.py:56-69`).

## 4. Market data fetch

Via `core.providers.upstox_provider.UpstoxProvider.get_historical_data`
(`core/providers/upstox_provider.py:228-303`), interval `"1day"`. Per
design rule 4(a): **every run re-fetches the full window from scratch for
every instrument** — candles are never appended to a prior run's stored
rows, because Upstox's own daily history is split-adjusted retroactively
(`research/b3_live_evidence_resolution_2026-09-26.md`, MCX evidence:
271/271 sessions show no split-sized break across a window that contains
a real 1:5 split). Appending would silently mix pre- and post-adjustment
values for the same historical dates across separate runs.

The provider validates `instrument_key` against
`core/providers/upstox_provider.py:96`
(`_INSTRUMENT_KEY_SEGMENT_PATTERN = re.compile(r"^[A-Z_]+\|.+$")`) and
percent-encodes it (`core/providers/upstox_provider.py:273`,
`quote(symbol, safe="")`) — this design assumes every `instrument_key`
produced by Section 3's mapping already satisfies that pattern (Upstox's
own `NSE_EQ|<ISIN>` / `NSE_INDEX|<name>` shapes both do, per the live
verification in `research/b3_live_evidence_resolution_2026-09-26.md`).

Returned `HistoricalCandle` objects
(`core/providers/base_provider.py` — not modified by this design) map to
`equity_intel.contracts.market_data.OHLCVObservation`
(`equity_intel/contracts/market_data.py:17-31`). Note:
`OHLCVObservation` has no `open` field at all (line 21-23's own
docstring: "`open` ... is never used by any component"), so the fetched
candle's `open` value is read from the provider but has no contract field
to persist into under the current schema — see Open Questions.

## 5. Data-quality checks

Existing, unimplemented-threshold functions in
`equity_intel/validation/framework.py` already cover most of this
scope, each returning `None` ("undecided") until a caller supplies a
threshold this design does not invent:

- Session count vs. requirement: `meets_minimum_history`
  (`equity_intel/validation/framework.py:61-67`) — takes
  `ValidationConfig.minimum_history_bars`
  (`equity_intel/validation/framework.py:26`), supplied by the caller,
  not fixed here.
- Zero-volume days: `has_usable_volume`
  (`equity_intel/validation/framework.py:70-87`) — takes
  `volume_usable_lookback` / `volume_usable_minimum_positive_bars`
  (`equity_intel/validation/framework.py:27-28`), also caller-supplied.
- Date alignment with the benchmark: not yet implemented anywhere in
  `equity_intel/validation/framework.py`; this design proposes a new
  function there (name/shape not fixed) that compares an instrument's
  observation-date set against the benchmark's observation-date set for
  the same fetch window, surfacing the same kind of date-list diff shown
  in `research/b3_live_evidence_resolution_2026-09-26.md` Section 2
  (Step 3's "identical set of 271 trading dates" comparison) per
  instrument instead of just for one symbol pair.
- **Corporate-action break detector** (design rule 4b — new, not yet
  implemented anywhere): a function that flags a session where
  `close[t] / close[t-1]` falls outside a threshold band, mirroring the
  ratio computation already done ad hoc in
  `research/b3_live_evidence_resolution_2026-09-26.md` (MCX: min 0.8834 /
  max 1.0724 across 271 sessions, no break; HEGAM: 0.3738 on the demerger
  date, a real break). Per design rule 4(b), a flagged instrument gets a
  degraded `DataStatus` and is **excluded from indicator computation**
  for that run — it is never adjusted. The threshold band itself, and
  which `DataStatus` value applies, are open questions (Section 10).

All of the above compose into
`equity_intel.contracts.quality.DataQualityResult`
(`equity_intel/contracts/quality.py:32-43`), using the frozen
`DataStatus` enum (`equity_intel/contracts/quality.py:25-29`:
`VALID`, `INSUFFICIENT_HISTORY`, `STALE`, `FAILED`). Note this enum has no
value that obviously means "corporate-action break detected" — see Open
Questions.

## 6. Feature computation

Only for instruments that pass Section 5's checks. Calls existing, pure
functions with no assumed periods:

- `equity_intel.indicators.trend.exponential_moving_average`
  (`equity_intel/indicators/trend.py:7-30`) — periods are caller-supplied,
  not fixed by B2's proposed 20/50/200.
- `equity_intel.indicators.momentum.relative_strength_index` and
  `rate_of_change` (`equity_intel/indicators/momentum.py:7-45`).
- `equity_intel.indicators.relative.relative_return`
  (`equity_intel/indicators/relative.py:7-25`) — against the benchmark
  series from Section 3/4.
- `equity_intel.indicators.volume.relative_volume`
  (`equity_intel/indicators/volume.py:7-30`) — returns `None`, never `0`,
  on any missing input.
- `equity_intel.indicators.structure.rolling_high` /
  `distance_from_high` (`equity_intel/indicators/structure.py:7-33`).
- `equity_intel.indicators.context.average_true_range` / `atr_percent`
  (`equity_intel/indicators/context.py:13-38`) — context-only, per its
  own docstring (line 3-6) never feeds a score.

Results populate `equity_intel.contracts.features.FeatureSet`
(`equity_intel/contracts/features.py:17-47`); every field stays
`Optional` and this design does not add a default anywhere `None` was
already possible.

## 7. Persistence

New module `equity_intel/persistence/connection.py` — the one path
`equity_intel/tests/test_db_connection_boundary.py:40-42`
(`ALLOWED_CONNECTION_MODULE`) already reserves and pre-authorizes for
`sqlite3` import. It must call
`equity_intel.persistence.db_path_guard.assert_allowed_db_path`
(`equity_intel/persistence/db_path_guard.py:27-44`) before opening any
connection — that guard accepts only the resolved
`<repo_root>/data/equity_intel.db` path (line 24) and refuses everything
else, including `:memory:`/`file:` shorthand (lines 35-38). This design
does not write `connection.py`'s implementation; it only fixes that this
is the single, already-reserved place it must live.

Tables to write into: `instruments`, `scan_runs`, `market_observations`,
`data_quality_results`, `feature_sets`
(`equity_intel/persistence/schema.py:23-84`) — none of these depend on a
B2 threshold. **Not written by v1**: `component_scores`,
`composite_scores`, `classification_results`, `scan_states`,
`paper_watchlist` (`equity_intel/persistence/schema.py:86-131`) — all are
downstream of scoring/classification/candidate selection, which stay
BLOCKED.

Repository interfaces already exist as abstract, unimplemented shapes in
`equity_intel/persistence/repositories.py`:
`UniverseRepository.list_members` (lines 22-30),
`MarketDataRepository.get_observations` /
`get_benchmark_observations` (lines 33-43),
`FeatureRepository.save_features` / `save_quality` (lines 46-53). This
design proposes concrete implementations of these four against
`connection.py`; `ScoreRepository`, `CandidateRepository`, and
`WatchlistRepository` (lines 56-83) stay unimplemented, matching their
own `NotImplementedError` messages.

## 8. Scan state and run tracking

`equity_intel.contracts.state.ScanState`
(`equity_intel/contracts/state.py:21-25`) is frozen to exactly `SCORED`,
`ELIGIBLE`, `CANDIDATE`, `WATCHLISTED` — every one of these names is
downstream of scoring (`equity_intel/contracts/state.py:10-14`'s own
docstring: entry into each depends on unresolved B2 decisions). **A v1
data-only scan run reaches none of these states for any instrument** —
there is currently no frozen `ScanState` value meaning "features computed,
not yet scored." This design does not invent one; see Open Questions.

Separately, `schema.py`'s `scan_runs` table
(`equity_intel/persistence/schema.py:36-44`) has a `status` column with
no defined vocabulary anywhere in this package. This is exactly the
"how is a failed or partial run recorded" open question (Section 10
below) — this design does not decide it, only confirms the column exists
and is currently unconstrained.

## 9. Entry point

`scripts/equity_scan.py` (new file, does not exist yet). Per
`equity_intel/scanner/shell.py:57-58`'s existing pattern, it must call
`equity_intel.scanner.execution_guard.assert_no_forbidden_modules_loaded`
(`equity_intel/scanner/execution_guard.py:39-53`) as its first action,
before constructing a `ScanPipeline` or touching any repository. This
design does not change `execution_guard.py`'s `FORBIDDEN_PREFIXES`
(`equity_intel/scanner/execution_guard.py:26-36`).

## 10. Open questions — not decided here

1. **B3-07 is still open.** May v1 use the benchmark's own returned
   session dates as a provisional trading calendar (in place of an
   official NSE holiday/session list), clearly labelled in output as
   provisional/unofficial? Today's evidence shows this can't simply be
   "weekdays minus holidays" — a real session fell on Sunday 2026-02-01
   (`research/b3_live_evidence_resolution_2026-09-26.md`, Section 2) — so
   even a provisional calendar must be a positive list of dates the
   benchmark actually returned, not a computed weekday filter.
2. **Break-detector thresholds** (Section 5): what ratio band flags a
   session as a possible corporate-action break? The two known real
   values are MCX's max daily move (7.24%, ordinary) and HEGAM's demerger
   move (−62.6%) — but nothing between those two points is evidenced.
   Also open: do F&O-eligible stocks (which trade under NSE's daily price
   bands) need a different threshold than non-F&O stocks (which may have
   wider circuit limits and no derivative-driven price discipline)?
3. **Upstox rate limits for ~500 sequential requests.** Per Upstox's own
   rate-limiting documentation (`https://upstox.com/developer/api-documentation/rate-limiting/`,
   fetched live for this design): historical-candle calls fall under
   "Other Standard APIs" (grouped with holdings/positions/funds, no
   separate historical-candle limit), documented as **50 requests/second,
   500 requests/minute, 2000 requests/30 minutes**. A ~500-symbol universe
   run sits right at the per-minute ceiling if run back-to-back with no
   pacing. Retry policy (what counts as retryable — a 429, a timeout, a
   5xx?), backoff shape, and how a persistently-failing single symbol
   should affect the rest of the run are all undecided.
4. **How a failed or partial run is recorded.** `scan_runs.status`
   (`equity_intel/persistence/schema.py:36-44`) exists but has no defined
   vocabulary (Section 8). Candidate shapes to consider — not chosen
   here — include a `RUNNING`/`COMPLETE`/`FAILED`/`PARTIAL`-style status
   column, or a per-instrument count of how many of the universe
   completed vs. failed within one `scan_id`. Whatever is chosen, the
   scope item "the dashboard later reads only `COMPLETE` scans" (Section
   0) means a run that stops partway through must never be
   indistinguishable from a fully completed one to a reader of
   `scan_runs`.

## 11. Decisions (Akshay, 2026-09-26)

1. **Calendar.** v1 uses the benchmark's returned session dates as a
   PROVISIONAL calendar, labelled provisional in the output, until B3-07
   closes.
2. **Break detector.** Flag a session where `close[t]/close[t-1] < 0.5`
   or `> 2.0`. Known gap: small demergers (ratio near 1) are not
   detected; a corporate-actions feed is deferred to v2.
3. **Flagged stocks are not excluded from the universe.** A flagged
   stock's history is truncated at the most recent break; indicators are
   computed only on sessions after the break; long-window features (any
   feature whose required lookback exceeds the post-break session count)
   come out `None`. Still flag, not adjust.
4. **Data status for a break.** An existing `DataStatus` value —
   `INSUFFICIENT_HISTORY` if too few post-break sessions remain,
   otherwise `VALID` — with a free-form `reason` recording the break date
   and ratio. No enum change.
5. **v1 writes no per-instrument `ScanState`.**
6. **`scan_runs.status` vocabulary.** `RUNNING -> COMPLETE | FAILED` (no
   `PARTIAL`). `FAILED` if the benchmark fetch fails, any `401` occurs, or
   the run crashes. `COMPLETE` only when every universe member has a
   `data_quality_results` row, set in the final transaction. The
   dashboard reads only the latest `COMPLETE` run.
7. **Rate limiting.** Pace at ~5 requests/second (Upstox: 500/min); retry
   `429`, timeouts, and `5xx` up to 3 times with backoff; other `4xx`
   errors fail that stock only; a `401` aborts the run.
8. **The open price is not stored in v1.**
9. **Provenance per run.** Each `scan_runs` row records the constituents
   file and the instrument-master file used, with their SHA-256.
10. **Indicator periods are display parameters**, allowed per
    `research/b2_b3_structural_build_boundary_audit_2026-09-22.md:179`:
    one explicit config with no code defaults; the values used are
    recorded on each `scan_runs` row; labelled "provisional, not
    B2-authoritative"; no bands, cutoffs, or scores are derived from
    them. v1 values: EMA 20/50/200, RSI 14, ROC 10, RVOL 20, rolling high
    252, ATR 14; `minimum_history_bars` 252 (from B3); volume usability
    15 of the last 20 bars (a provisional flag, from B2 D04). Note: these
    reuse the B2-proposed periods; they bind nothing for B2.

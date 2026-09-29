# Equity Intelligence Scanner V1 — Frozen Spec

Status: FROZEN. Recorded 2026-09-27 (Akshay). This document is authoritative
for the V1 scanner and read-only dashboard. It **supersedes the parts of
`docs/architecture/equity_scanner_v1_design.md` listed in Section 11** below;
everything in that doc not listed there still stands (universe/ISIN mapping,
provisional calendar, DUMMY*/BE-series universe filtering, pacing/retry
policy, per-run provenance hashing).

Paper/research only. No broker order APIs, no positions, no trading engine,
no order router. B2 scoring is BLOCKED — every scan and every dashboard view
shows `SCORING_STATUS = BLOCKED_B2`. A missing score is never shown or
treated as zero.

## 1. Pipeline

```
Universe -> Calendar -> Price acquisition -> Candle validation
   -> Immutable snapshots -> Symbol classification + review flags
   -> ScanRun completion -> [B2 scoring: BLOCKED]
```

Indicator/feature computation is **out of scope for V1**. This scanner does
not compute or store any indicator (`equity_intel/indicators/` and its
existing tests are untouched, kept for a later phase, not wired into this
pipeline).

## 2. Universe

- Source: the NIFTY 500 constituent CSV (`data/reference/nifty500_constituents_*.csv`).
  The CSV's `Industry` field is the v1 sector.
- `universe_version` recorded on every `ScanRun` = SHA-256 hash of the CSV file.
- Row filtering (carried forward from `equity_scanner_v1_design.md` §2,
  confirmed 2026-09-27): exclude any row whose `Symbol` matches `DUMMY*`;
  flag (do not exclude) any row whose `Series` is not `EQ` — recorded on the
  symbol as `NON_EQ_SERIES`. Excluded (`DUMMY*`) rows and the exclusion
  reason are recorded on the `ScanRun` (`excluded_symbols`), not silently
  dropped.
- Instrument mapping: by ISIN, against the Upstox `NSE_EQ`-segment
  instrument master (carried forward from `equity_scanner_v1_design.md` §3).
  A symbol whose ISIN has no instrument-master match is never dropped from
  the universe: it is classified `FAILED` with a `status_reason` naming the
  unmatched ISIN.

## 3. Calendar (B3-07, frozen)

- Benchmark `NSE_INDEX|Nifty 500` daily candles are the authoritative
  trading calendar for V1.
- No NSE holiday file in V1. `calendar_verification = "UNVERIFIED_INDEX_ONLY"`
  on every `ScanRun`.
- Market-open days are never inferred from any individual stock.
- `SESSION_CUTOFF_IST = 18:00` (config constant) — an operational
  convention, not proof that data is final.
- `latest_closed_session` = the most recent index candle date where
  `(date < today) OR (date == today AND now >= SESSION_CUTOFF_IST)`.
- If the index fetch fails, is empty, or cannot be parsed: the `ScanRun`
  ends `ABORTED` with `abort_reason = CALENDAR_INVALID`, and no symbols are
  classified.
- Persisted on the `ScanRun`: `calendar_source`, `calendar_verification`,
  `latest_closed_session`, and the calendar dates used
  (`calendar_dates`).

## 4. History window

`REQUIRED_SESSIONS = 252` (config constant; ties to the pre-existing
`w52_complete` concept).

## 5. Candle validation (per candle -> `candle_validation_status`)

Structural checks only: missing fields/nulls, `high < low`, `open` or
`close` outside `[low, high]`, non-positive prices, negative volume. No
statistical or jump thresholds. `candle_validation_status` is `VALID` or
`INVALID`; a specific failing check is recorded in `validation_errors`.

## 6. Symbol classification (per symbol -> `symbol_data_status`)

Checked in this order; first match wins:

1. `FAILED` — acquisition, parsing, or storage failed (network/API error,
   bad response, unmatched instrument mapping).
2. `INSUFFICIENT_HISTORY` — fewer than `REQUIRED_SESSIONS` valid candles
   available.
3. `STALE` — latest valid candle date < `latest_closed_session`. Zero
   tolerance.
4. `VALID` — otherwise.

Network failure is never classified `INSUFFICIENT_HISTORY`. Missing data is
not stale data.

Also recorded: `available_session_count`, `missing_session_count` (calendar
sessions in the window with no valid candle). `missing_session_count > 0`
sets flag `HISTORY_GAPS`. A symbol can be `VALID` and still carry
`HISTORY_GAPS`. No maximum gap count is defined.

### Flags (independent of `symbol_data_status` and of each other)

- **`HISTORY_GAPS`** — see above.
- **`NON_EQ_SERIES`** — the universe row's `Series` is not `EQ` (§2).
- **`PRICE_BREAK_DETECTED`** — a session where
  `close[t]/close[t-1] < 0.5` or `> 2.0` (carried forward from
  `equity_scanner_v1_design.md` §11 decision 2, **narrowed to a flag only**:
  see Section 11). Unlike that superseded decision, V1 **never truncates**
  history at the break and **never excludes** the symbol from indicator
  computation (indicators are out of scope entirely — Section 1). The break
  is reported; nothing downstream reacts to it automatically.
- **`CORPORATE_ACTION_REVIEW`** — see Section 7.

## 7. Corporate-action review (manual list, no automation)

- Manually maintained CSV at `data/reference/corporate_action_review.csv`.
  Fields: `symbol`, `isin` (optional), `event_type`, `effective_date`,
  `reason`, `reviewer`, `review_state`.
- **This file must always exist.** Header-only (no data rows) is allowed
  when there are no entries under review — that is the normal, valid state,
  not an error. The file's *absence*, or any failure to read/parse it, is
  different: if the review CSV is missing or unreadable, the run ends
  `ABORTED` with `abort_reason = CORPORATE_ACTION_REVIEW_CSV_INVALID`, the
  same way an invalid calendar aborts the run with `CALENDAR_INVALID`
  (Section 3). Missing-file and empty-file are not the same case and must
  not be conflated: an empty (header-only) file legitimately means "review
  every symbol's window against zero pending entries"; a missing or
  unreadable file means the scanner cannot know whether that's true, so it
  must not proceed and guess.
- If an entry is not `RESOLVED` and its `effective_date` falls inside the
  symbol's fetched window, flag `CORPORATE_ACTION_REVIEW`.
- Independent of `symbol_data_status`.
- No automatic price-jump detection feeds this flag (that is
  `PRICE_BREAK_DETECTED`, Section 6, a separate mechanism). No automatic
  demerger or split adjustment. This CSV is not persisted into
  `data/equity_intel.db` as its own table — it is read from disk once per
  scan run and applied to that run's symbol results; the DB stores only the
  resulting flag.
- `corporate_action_review_version` recorded on every `ScanRun` = SHA-256
  hash of `data/reference/corporate_action_review.csv`, the same treatment
  as `universe_version` (Section 2) — provenance of which review-list
  revision produced that run's `CORPORATE_ACTION_REVIEW` flags.

## 8. Immutable snapshots

- Append-only. Every fetched candle is stored as a `PriceFetchSnapshot` tied
  to exactly one `scan_run_id`. Earlier snapshots are never updated or
  deleted.
- Fields: `scan_run_id`, `symbol`, `trading_date`, `source`,
  `fetched_at_ist`, `open`, `high`, `low`, `close`, `volume`,
  `content_hash`, `candle_validation_status`, `source_metadata`.
- `UNIQUE (scan_run_id, symbol, trading_date, source)`. Retries inside the
  same run must not duplicate.
- `scan_run_id` is a foreign key into `scan_runs(run_id)`, enforced (`PRAGMA
  foreign_keys = ON` on every connection — see Section 9): a snapshot for a
  `scan_run_id` that does not exist is refused, not silently orphaned.
- Canonical hash: SHA-256 of `"YYYY-MM-DD|open|high|low|close|volume"`;
  prices as `Decimal` quantized to 2dp with `ROUND_HALF_UP`; volume as
  integer; null represented as empty string.
- Stores normalized values + hash + source metadata. Never the full raw
  vendor payload.
- **Stored form matches the hash input exactly.** `open`/`high`/`low`/
  `close` are persisted as `TEXT`, holding the same 2dp-quantized decimal
  string used to build `content_hash` — never a `REAL`/float column, which
  could silently re-round or drop trailing zeros. E.g. an input of `100.5`
  is quantized and stored as the string `"100.50"`, and that exact string
  is what `content_hash`'s input string is built from. Phase 2 (the
  snapshot writer) must include a test proving this: writing `100.5` in
  produces the stored value `"100.50"`, and recomputing the canonical hash
  from the stored row reproduces the same `content_hash` that was written.

## 9. `ScanRun` (run-level audit)

Fields: `run_id`, `started_at`, `finished_at`, `status`, `abort_reason`,
`universe_version`, `corporate_action_review_version`, `benchmark`,
`calendar_source`, `calendar_verification`, `latest_closed_session`,
`calendar_dates`, `price_source`, `requested_symbols`,
`successful_symbols`, `failed_symbols`, `status_counts`, `flag_counts`,
`excluded_symbols`, `errors`, `git_commit`, `git_dirty`, `scoring_status`
(always `BLOCKED_B2`).

- Status lifecycle: `RUNNING -> COMPLETE | ABORTED` (no `PARTIAL`, no
  `FAILED` at the run level — `FAILED` is reserved for `symbol_data_status`).
- `COMPLETE` means every requested symbol has a persisted outcome
  (including `FAILED` ones) — processing finished, not that all data is
  good. Set only in the final transaction.
- **A `ScanRun` cannot be marked `COMPLETE` unless both `universe_version`
  and `corporate_action_review_version` are set.** Enforced at the DB
  level, not just by application code: `scan_runs` carries a `CHECK`
  constraint (`equity_intel/persistence/schema.py`) rejecting any row where
  `status = 'COMPLETE'` and either provenance hash is `NULL`. A `RUNNING`
  or `ABORTED` row is not held to this — a run can abort before it ever
  reaches universe/review-list loading.
- On scanner start, any `ScanRun` still `RUNNING` from before is marked
  `ABORTED` (`abort_reason = INTERRUPTED`).
- One bad symbol never aborts the whole scan.
- A `401` from the price vendor aborts the run: `abort_reason = AUTH_FAILED`.
- A missing or unreadable `corporate_action_review.csv` aborts the run:
  `abort_reason = CORPORATE_ACTION_REVIEW_CSV_INVALID` (Section 7).
- Rate limiting: pace at ~5 requests/second; retry `429`, timeouts, and
  `5xx` up to 3 times with backoff; other `4xx` fails that symbol only
  (`FAILED`, with the reason recorded); retries exhausted -> that symbol
  `FAILED`; a `401` aborts the run as above. (Carried forward from
  `equity_scanner_v1_design.md` §11 decision 7 — not narrowed, not
  superseded.)
- **A finished `ScanRun` is frozen at the DB level.** A `scan_runs` row is
  never deleted (`BEFORE DELETE` trigger, unconditional), and once a row
  leaves `RUNNING` (i.e. becomes `COMPLETE` or `ABORTED`) no field of it may
  ever change again — including flipping `status` back to `RUNNING`
  (`BEFORE UPDATE ... WHEN OLD.status != 'RUNNING'` trigger). The normal
  `RUNNING -> COMPLETE`/`ABORTED` transition itself is unaffected, since it
  fires while `OLD.status` is still `RUNNING`.
- **A `symbol_scan_results` row may only be written while its owning run is
  `RUNNING`.** Once that `ScanRun` is `COMPLETE` or `ABORTED`, none of its
  symbol results may be inserted, updated, or deleted — enforced by triggers
  on `symbol_scan_results` that check the parent `scan_runs.status`. Every
  symbol result is written during the run that produced it, never added or
  edited afterward.
- Every connection opens with `PRAGMA foreign_keys = ON`
  (`equity_intel/persistence/connection.py`): both
  `price_fetch_snapshots.scan_run_id` and `symbol_scan_results.scan_run_id`
  are foreign keys into `scan_runs(run_id)` — a write referencing a
  `scan_run_id` that does not exist is refused.
- `initialize_schema()` is not a silent no-op on a version mismatch: if
  `data/equity_intel.db` already has a `schema_version` row whose value
  differs from the code's `SCHEMA_VERSION`, it raises
  `SchemaVersionMismatch` rather than proceeding against a database it does
  not actually match. Table/trigger creation for a fresh database happens
  inside one explicit transaction, so a failure partway through leaves no
  partial schema behind.

## 10. Dashboard (part of V1, READ-ONLY)


Separate Flask app at top-level `dashboard/` (outside `equity_intel/`, so
the package's own `sqlite3`-import boundary test does not need to special-
case it — see Section 12 on the boundary-test extension). It reads
`data/equity_intel.db` only, through a dedicated read-only connection
function in `equity_intel/persistence/connection.py`
(`get_read_only_connection`), and performs no writes of any kind.

Frozen routes: `/equity`, `/api/equity/summary`, `/api/equity/candidates`,
`/api/equity/sectors`, `/api/equity/stock/<symbol>`.
`/api/equity/candidates` returns `SCORING_STATUS = BLOCKED_B2` and no
ranking. Approved extra route: `/api/equity/scan-history`.

Four sections: Overview (latest `COMPLETE` run, its age, status/flag
counts, calendar source + verification, `BLOCKED_B2` banner); Stock
explorer (paginated, searchable: status, flags, missing sessions, latest
candle, source); Stock details (bounded candle history, missing dates,
flags, fetch history); Scan history (past runs: counts, errors, git commit,
universe hash).

Shows only the latest `COMPLETE` run. If that run's `latest_closed_session`
is older than the current latest closed session, show a prominent
"OUTDATED" warning. Never presents an old scan as current.

No scan-launch buttons. No watchlist editing. No snapshot comparison view
(deferred to V1.1). Indexed queries and pagination only — never all
snapshot rows loaded into the browser.

## 11. What this document supersedes in `equity_scanner_v1_design.md`, and why

Recorded 2026-09-27, per Akshay's explicit Phase-0 answers:

1. **Corporate-action break detection with history truncation** (§11
   decision 2–4 of the superseded doc: truncate history at the break,
   compute indicators only on post-break sessions, `INSUFFICIENT_HISTORY`
   or `VALID` with a free-form reason). **Superseded.** V1 keeps only the
   detection ratio (`< 0.5` or `> 2.0`) as a **flag**
   (`PRICE_BREAK_DETECTED`, Section 6) — no truncation, no automatic
   exclusion from anything. Reason: the new frozen spec forbids automatic
   price-jump detection *driving* symbol handling; detection-as-flag is
   kept because Akshay approved it explicitly as a flag-only mechanism on
   2026-09-27, alongside the separate manual `CORPORATE_ACTION_REVIEW` list
   (Section 7).
2. **Volume-usability rule** ("15 of the last 20 bars", §11 decision 10 of
   the superseded doc, presented there as an approved provisional flag).
   **Superseded — not implemented in V1.** Not approved per the new frozen
   spec; deferred to B2.
3. **Indicator/feature-computation pipeline stage** (§1, §6 of the
   superseded doc: EMA/RSI/ROC/relative-return/relative-volume/ATR computed
   as stage 4, backed by a `feature_sets` table). **Superseded — out of
   scope for V1.** The new frozen spec's pipeline (Section 1 above) ends at
   symbol classification; there is no feature-computation stage. The
   `equity_intel/indicators/` modules and their existing tests are
   untouched but not called by this pipeline.
4. **"Full re-fetch of the window every run (never append)"**
   (`research/b3_live_evidence_resolution_2026-09-26.md`, design rule 4a,
   carried into `equity_scanner_v1_design.md` §4: "every run re-fetches the
   full window from scratch... candles are never appended to a prior run's
   stored rows"). **Superseded by the append-only snapshot policy**
   (Section 8 above). That rule was written to solve a real problem —
   Upstox's daily history is retroactively split-adjusted, so mixing
   pre- and post-adjustment values for the same historical date *within a
   single stored series* would silently corrupt it. The frozen spec solves
   the same problem differently: instead of one mutable per-instrument
   series that must never mix adjustment regimes, V1 stores every fetched
   candle as its own immutable, append-only `PriceFetchSnapshot` keyed by
   `(scan_run_id, symbol, trading_date, source)`. Two runs fetching the same
   `trading_date` produce two separate rows, one per `scan_run_id`, each
   frozen at the adjustment state Upstox returned for that run — never
   merged, never overwritten (Section 8's DB-level triggers enforce this).
   The original rule's *intent* (never let a stale adjustment silently mix
   with a fresh one) is preserved; its *mechanism* (re-fetch instead of
   append, because there was only one mutable row to protect) no longer
   applies once every write is its own immutable row.

Everything else in `equity_scanner_v1_design.md` and
`research/b3_live_evidence_resolution_2026-09-26.md` (universe/ISIN
mapping, provisional calendar as a positive session list, `DUMMY*`/`BE`-
series filtering, pacing/retry/401-abort policy, per-run provenance
hashing) is carried forward unchanged and is not superseded.

### Where superseded-doc concepts are actually persisted in V1 (not a new table)

- **ISIN → `instrument_key` mapping, `DUMMY*` exclusion, non-`EQ`-series
  flag** (previously the `instruments` table): `instruments` is not
  recreated. A symbol's `instrument_key`, `isin`, `series`, `company_name`,
  and `sector` are recorded per run on `symbol_scan_results` (Section 9 of
  the schema doc / `equity_intel/persistence/schema.py`) — every symbol
  that reaches classification carries its own identity fields for that run,
  and `non_eq_series_flag` is a column there. `DUMMY*` rows never reach
  `symbol_scan_results` at all (they are excluded from the universe before
  fetching); they are recorded instead on the owning `ScanRun`'s
  `excluded_symbols` field, with the exclusion reason.
- **`PRICE_BREAK_DETECTED` / `CORPORATE_ACTION_REVIEW`** (Sections 6–7):
  both are boolean columns on `symbol_scan_results`
  (`price_break_detected_flag`, `corporate_action_review_flag`). The manual
  CSV review list itself (Section 7) is not mirrored into its own DB table
  — it is source data read from disk once per run; only its *effect* (the
  flag) is persisted, the same way the universe CSV itself is not stored in
  the DB, only its derived `universe_version` hash and per-symbol fields
  are.

## 12. Note on the persistence-boundary test extension

`equity_intel/tests/test_db_connection_boundary.py` currently only scans
`equity_intel/`. Per Akshay's Phase-0 answer (h), the equivalent
`sqlite3`-import and forbidden-DB-path guarantees must also cover
`dashboard/` once it exists. That test extension (and the `dashboard/`
package itself) lands in Phase 4, not this phase — `dashboard/` does not
exist yet, so there is nothing to extend the test to cover until then.

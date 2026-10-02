# B3 SOURCE RESOLUTION & INSTRUMENT MAPPING — 2026-09-22

Controlled verification task. Read-only against the repository except for
this single new document. External web sources were consulted (per this
task's explicit authorization) to verify official source identity and
documented mechanisms; no constituent, price, volume, benchmark, or
sector dataset was downloaded or persisted into this repository.

## 1. Preflight

- HEAD: `03ccce95ff47af479d9382723ae91694d39fb6a2` (confirmed unchanged
  from the two prior B3 tasks)
- Branch: `main` (unchanged)
- Pre-existing modified: 136
- Pre-existing staged: 0
- Pre-existing untracked: 132 (matches the prior task's own post-audit
  count exactly — no drift between tasks)

## 2. Human Decisions Being Verified

- D-B3-01 Universe: NIFTY 500 stocks
- D-B3-02 Vendor: UPSTOX
- D-B3-03 Benchmark: NIFTY 500 index
- D-B3-04 Sector mapping: authoritative NSE/Nifty Indices source
- D-B3-05 History basis: 252 trading sessions
- D-B3-06 Acquisition: approved in principle, not authorized this task

This task does not alter, re-litigate, or add to these decisions. It
attempts only to verify the source/mechanism layer beneath them.

## 3. B3-01 — NIFTY 500 Constituent Source

**External sources consulted:**

- NSE India, "Nifty 500 Index" (official product page),
  https://www.nseindia.com/static/products-services/indices-nifty500-index,
  accessed 2026-09-22. Fact verified: NSE Indices is confirmed as
  publisher; the page states the NIFTY 500 "represents the top 500
  companies based on full market capitalisation from the eligible
  universe" and covers ~92.04% of NSE free-float market cap as of
  2026-03-30; the page shows a revision marker "Updated on: 22/04/2026";
  the page offers a downloadable constituent CSV, a methodology PDF, and
  a factsheet PDF.
- NSE Indices / NSE Archives, "Nifty 500 Index" factsheet PDF,
  https://nsearchives.nseindia.com/content/indices/ind_nifty_500.pdf,
  accessed 2026-09-22. Fact verified: publisher is NSE Indices Limited
  (formerly IISL); methodology is free-float market capitalization;
  reconstitution is semi-annual, effective the first business day
  following January 31 and July 31 of each year, announced four weeks in
  advance; inclusion/exclusion criteria are turnover- and market-cap-rank
  based.
- NSE Indices, index constituent download endpoint referenced by the
  above official page: `https://niftyindices.com/IndexConstituent/ind_nifty500list.csv`
  (identified via search of the official nseindia.com page's own linked
  resources; **not fetched** — per this task's explicit prohibition on
  downloading/persisting the constituent dataset). Fact verified: this is
  the same CSV download endpoint pattern NSE Indices uses for its other
  published index constituent lists (e.g. the NIFTY 200 equivalent,
  `ind_nifty200list.csv`, was independently observed at the same host
  during this search), which supports it being the correct, standard,
  reproducible endpoint pattern for NIFTY 500 as well — but the NIFTY 500
  file's own byte content, current row count, and header schema were NOT
  independently opened in this task.
- Secondary, non-official source (used only to describe the CSV's known
  column schema, not as a source-of-truth for the classification
  requirement itself): Rohith, "Analyzing NIFTY 500," Medium,
  https://hithro.medium.com/analyzing-nifty-500-4ea13c4fdb1f, accessed
  2026-09-22. Reports the CSV contains: Company Name, Industry, Symbol,
  Series, ISIN Code. This is a third-party description, not confirmed
  against the official file itself in this task, and is recorded here as
  SECONDARY / UNCONFIRMED.

**Verification answers:**

1. Official source identity — VERIFIED: NSE Indices Limited, via
   nseindia.com and the niftyindices.com download domain it links to.
2. Exact page/download endpoint — VERIFIED (page); endpoint URL pattern
   identified but not fetched/opened.
3. Actually represents NIFTY 500 — VERIFIED (official page and factsheet
   both describe this specific 500-company index).
4. Provides the constituent list — VERIFIED as an offer (downloadable
   CSV is present on the official page); content not inspected.
5. Effective/as-of/version marker — VERIFIED: the official page displays
   a revision date ("Updated on: 22/04/2026"), and reconstitution dates
   (Jan 31 / Jul 31 each year) are documented in the factsheet.
6. Reproducible for a specified scan date — PARTIAL: the current
   constituent list is deterministically obtainable at a stated revision
   date; whether NSE Indices separately publishes POINT-IN-TIME
   historical constituent lists for past reconstitution dates (needed to
   reproduce a scan run from a prior date) was NOT verified — the
   official page and factsheet describe the current/forward
   reconstitution schedule, not an archive of past lists.
7. Symbols mappable to Upstox — see Section 4; PARTIAL, mechanism
   identified, not exercised.
8. Historical constituent membership representable — UNRESOLVED per
   item 6 above.

**B3-01 = PARTIALLY RESOLVED.** The official source is identified,
named, and its current-list reproducibility is documented. It is not yet
fully resolved: (a) the file itself was never opened to confirm its
actual schema/content in this task, and (b) point-in-time historical
constituent availability (needed for reproducible past-date scans, not
just "today") is unconfirmed. Neither gap requires further web research
to close — both are closed only by an actual (future, out-of-scope-here)
inspection/acquisition step.

## 4. B3-02 — Constituent to Upstox Mapping

**External sources consulted:**

- Upstox, "Instruments" developer documentation,
  https://upstox.com/developer/api-documentation/instruments/, accessed
  2026-09-22. Fact verified: Upstox publishes machine-readable instrument
  master files (JSON preferred; CSV deprecated) refreshed daily around
  6 AM IST; fields include `instrument_key`, `trading_symbol`,
  `exchange_token`, `segment` (e.g. `NSE_EQ`, `BSE_EQ`, `NSE_FO`),
  `instrument_type` (`EQ`, `FUT`, `CE`, `PE`, `INDEX`, `BE`), `isin`,
  `name`, `lot_size`, `tick_size`, `freeze_quantity`; NSE equity (cash)
  instruments are explicitly documented with worked examples, alongside
  separate index-instrument examples — i.e. equities and indices are
  both covered by the same documented mechanism, not one only.
- Upstox, "Search Instruments API" developer documentation,
  https://upstox.com/developer/api-documentation/instrument-search/,
  accessed 2026-09-22. Fact verified: a free-text, case-insensitive
  search endpoint exists over the same instrument catalogue, filterable
  by `segments`, returning `instrument_key`, `trading_symbol`,
  `instrument_type`, `isin`, and related fields — an alternative,
  query-based route to the same identifiers as the bulk master file.
- Upstox Community, "How to Access Full NSE Equity Instruments JSON File
  (with trading_symbol and instrument_key)?",
  https://community.upstox.com/t/how-to-access-full-nse-equity-instruments-json-file-with-trading-symbol-and-instrument-key/9179,
  accessed 2026-09-22. Fact noted (developer-reported, not official):
  one developer reported that some published `.gz` instrument files in
  practice omit `trading_symbol` for certain records, meaning the
  documented schema and the file's actual observed content have, at
  least once, diverged in an unspecified way. This is a caveat, not
  something this task independently confirmed either way.

**Deterministic mapping procedure identified (not executed):**

1. Obtain the NIFTY 500 constituent list for the scan's as-of date
   (Section 3), which — per the secondary source noted there — is
   reported to include an ISIN Code column alongside Company Name,
   Industry, Symbol, and Series.
2. Obtain Upstox's same-day instrument master, filtered to
   `segment == "NSE_EQ"` and `instrument_type == "EQ"`.
3. Join primarily on ISIN (present in both, per the sources above,
   subject to the schema-divergence caveat), falling back to an
   exact `trading_symbol` match only where ISIN is unavailable, since
   ISIN is exchange- and renaming-invariant while a trading symbol is
   not.
4. Any NIFTY 500 constituent with no ISIN match and no exact symbol
   match must be recorded as an explicit, reported mapping failure —
   never silently dropped or fuzzy-matched.
5. Renamed/relisted securities are handled by ISIN continuity (ISIN
   generally survives a corporate rename; this is standard market
   practice, not independently confirmed against an NSE renaming
   case in this task).
6. Duplicate/ambiguous symbols (e.g. a symbol reused across series or
   over time) are resolved by requiring both ISIN and `segment ==
   NSE_EQ` to match — never resolved by symbol string alone.
7. This procedure requires no per-symbol manual maintenance: steps
   1-4 are mechanically reproducible from the two published sources
   for any given scan date, provided both files are pulled and their
   actual (not just documented) schemas are confirmed at acquisition
   time.

**B3-02 = MECHANISM IDENTIFIED, NOT VERIFIED END-TO-END.** The mapping
procedure above is deterministic on paper and grounded in officially
documented fields from both sources. It has not been exercised: neither
file's actual current content was opened in this task, and the community
report of a schema gap (`trading_symbol` sometimes missing) means the
procedure's step 3 fallback needs to be validated against the real file
before being relied upon.

## 5. B3-03 — NIFTY 500 Benchmark Instrument

**External sources consulted:**

- Upstox, "Search Instruments API" documentation (as cited in Section
  4). Fact verified: index instruments are covered by the same search
  mechanism, with a documented response example for "Nifty 50" showing
  `segment = NSE_INDEX`; searching by `segments=INDEX` or by query text
  is the documented way to locate an index instrument generically —
  this describes the correct MECHANISM for locating NIFTY 500, not the
  NIFTY 500 result itself.
- Upstox (consumer site, not developer API docs), "Nifty 500 Today,"
  https://upstox.com/indices/nifty-500-share-price/, accessed
  2026-09-22. Fact observed: this consumer-facing page repeatedly labels
  the index `INDEXNSE:NIFTY_500`. This identifier string appears on
  Upstox's own public website in connection with the NIFTY 500 index.

**Why this does not resolve B3-03:** `INDEXNSE:NIFTY_500` is a
consumer-site display/quote symbol, not confirmed to be the Developer
API `instrument_key` string (which, per Section 4's documented examples
and per this repository's own already-confirmed NIFTY 50 key
`"NSE_INDEX|Nifty 50"`, follows a different format:
`"<SEGMENT>|<display name>"`, not a colon-joined ticker). No official
Upstox developer-API documentation page found in this task explicitly
lists a NIFTY 500 index `instrument_key` value. Per this task's explicit
instruction, that string is NOT recorded as the verified `instrument_key`
— doing so would be guessing.

**Result: BENCHMARK INSTRUMENT MAPPING UNRESOLVED.** What IS verified:
(a) NSE Indices officially operates and publishes the NIFTY 500 index
itself (Section 3), so the underlying benchmark exists and is real; (b)
Upstox's documented Search Instruments API and instrument master
mechanism are both confirmed capable, in principle, of returning an
index's exact `instrument_key` when queried by name or by
`segment=NSE_INDEX`. What is NOT verified: the actual `instrument_key`
value Upstox assigns to the NIFTY 500 index, and whether historical
daily candles are available for it back far enough to satisfy the
Relative Strength lookback (this cannot be checked without first
resolving the instrument_key and then calling the historical-candle
endpoint, both out of this task's scope).

## 6. B3-04 — Sector Mapping

**External sources consulted:**

- NSE India, "Industry Classification,"
  https://www.nseindia.com/static/products-services/industry-classification,
  accessed 2026-09-22. Fact verified: NSE Indices' formal industry
  classification is a 4-tier taxonomy — 12 Macro-Economic Sectors, 22
  Sectors, 59 Industries, 197 Basic Industries. Critically, this page
  states it does NOT offer a downloadable per-company/per-symbol mapping
  file — only the methodology/structure PDF is downloadable, and the
  page directs anyone wanting the actual constituent-to-classification
  data to contact NSE Indices Ltd. directly ("indices@nse.co.in") for
  "related queries and subscription."
- NSE Indices, "Industry Classification Guideline," July 2023,
  https://www.niftyindices.com/docs/default-source/default-document-library/nse-indices_industry-classification-guideline-2023-07.pdf,
  accessed 2026-09-22. Fact verified: publisher NSE Indices Limited;
  classification methodology uses audited consolidated financial
  statements, primarily revenue share (>50% of revenue in one segment,
  else "Diversified" if multiple segments are each ≥20%); annual review
  cycle following receipt of audited annual reports; document is
  methodology only, not a data file, and does not name NIFTY 500
  specifically (it applies to "all companies listed on NSE").
- Secondary source (Section 3): the NIFTY 500 constituent CSV itself is
  reported (third-party, unconfirmed against the official file in this
  task) to include a per-row "Industry" column. If accurate, this would
  supply a coarser, single-field classification bundled directly with
  the universe file — distinct from, and shallower than, the formal
  4-tier taxonomy above, and its exact taxonomy version/vintage would
  still need to be established at acquisition time.

**Result: SOURCE PARTIALLY IDENTIFIED, MAPPING NOT PUBLICLY VERIFIED.**
The authoritative classification framework and its publisher are now
named and documented (this was previously a total blank per the prior
audit). However, the requirement in D-B3-04 — "every NIFTY 500
constituent must have an explicit sector mapping" from "an authoritative
NSE/Nifty Indices classification source" — cannot yet be satisfied
deterministically and publicly: NSE Indices' own page states the full
4-tier mapping is subscription/request-only, not a public download. The
one candidate free path (an "Industry" column allegedly bundled in the
NIFTY 500 constituent CSV) is unconfirmed and, if real, is a shallower
classification than D-B3-04 may require depending on how "sector" is
ultimately defined against the four tiers. This is a governance question
(which tier of NSE's taxonomy counts as "the sector mapping," and
whether the free bundled column or the subscription taxonomy is
required) that this task cannot resolve — it is a human decision, not a
technical one, and is recorded here as a new open sub-item rather than
answered.

## 7. B3-07 — 252-Session Calendar

**External sources consulted:**

- NSE India, "Market Timings & Holidays,"
  https://www.nseindia.com/resources/exchange-communication-holidays,
  accessed 2026-09-22. Fact verified: this is NSE's own official
  Exchange Communications resource for trading/clearing holidays,
  segmented by product (Capital Market, Derivatives, Electronic Gold
  Receipts, Debt Market) and selectable by year; it distinguishes
  "Trading Holidays" from "Clearing Holidays" and separately notes
  special/truncated sessions (e.g. Diwali Muhurat trading). Saturdays
  and Sundays are the standard non-trading days outside this list.

**Verification answers:**

1. Official calendar source — VERIFIED: NSE's own Exchange
   Communications page, Capital Market segment is the correct segment
   for equity trading sessions.
2. Equity-market applicability — VERIFIED (Capital Market segment
   selectable explicitly).
3. Holiday handling — VERIFIED as documented (a stated list per year).
4. Weekend handling — VERIFIED (Sat/Sun implicitly excluded as
   standard, confirmed by the page's framing).
5. Special sessions — VERIFIED as documented (e.g. Muhurat trading
   noted as a distinct, special case, not a normal or a non-trading
   day).
6. Deterministic session enumeration — PARTIAL: the page is a
   browsable, year-selectable reference page rather than a single
   structured downloadable file (e.g. no confirmed CSV/JSON export was
   found in this task); an automated pipeline would need to parse this
   page (or find/confirm an equivalent structured export) at
   acquisition time.
7. 252 completed sessions selectable reproducibly — NOT YET
   ESTABLISHED: this depends on item 6's automated-extraction gap being
   closed first.
8. Current-session inclusion determinism — NOT YET ESTABLISHED, same
   dependency.
9. Relationship to B2's own 252-session/52-week completeness
   requirement — unchanged from the prior audit; this task did not
   touch B2.

**B3-07 = SOURCE IDENTIFIED, MECHANISM NOT FULLY ESTABLISHED.** This
closes the largest part of the prior "no source at all" gap: NSE's
official holiday resource is now named and confirmed. What remains open
is purely mechanical — confirming a structured, programmatically
reproducible export of that calendar (or documenting a page-scraping
procedure) — not a question of finding the source.

## 8. Upstox OHLC/Volume Capability

No new external verification was needed here beyond what the prior two
B3 tasks already established from this repository's own code:
`core/historical_data.py` confirms, via its own module-level comment
(itself stated to be "confirmed via Upstox's own developer docs, not
assumed" at the time it was written), the V3 historical-candle endpoint
`GET /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}`
with `unit=days`, `interval=1` as a valid combination for daily candles,
and confirms the returned row shape includes `open, high, low, close,
volume, oi`. This is generic over `instrument_key` — nothing in the
endpoint's own contract restricts it to the NIFTY 50 index this repo
currently calls it with.

This task's new finding (Section 4) adds that Upstox's instrument
master/search mechanism documents NSE equity (`NSE_EQ`) instruments with
worked examples, meaning the `instrument_key` inputs the historical
candle endpoint needs ARE, in principle, obtainable for equities the
same documented way they were obtained for the NIFTY 50 index.

**Equity OHLC: MECHANISM VERIFIED IN PRINCIPLE, NOT EXERCISED.**
**Equity volume: MECHANISM VERIFIED IN PRINCIPLE, NOT EXERCISED** (same
endpoint, same row shape, includes `volume`).
**Benchmark history:** blocked upstream of this — the benchmark
`instrument_key` itself is unresolved (Section 5), so its historical
candle availability cannot yet be checked at all.
**Instrument lookup:** VERIFIED as a real, documented Upstox mechanism
(bulk master file and/or Search Instruments API), not yet exercised
against either an equity symbol or the NIFTY 500 index.

## 9. Source Traceability Matrix

| Requirement | Official Source | Exact Source/Identifier | Verified? | Reproducible? | Remaining Gap |
|---|---|---|---|---|---|
| B3-01 NIFTY 500 universe | NSE Indices Ltd. | nseindia.com NIFTY 500 index page; niftyindices.com/IndexConstituent/ind_nifty500list.csv | PARTIAL | PARTIAL | File content unopened; point-in-time historical lists unconfirmed |
| B3-02 constituent → Upstox mapping | Upstox Developer API | Instrument master (JSON, daily ~6AM refresh) / Search Instruments API | PARTIAL | PARTIAL | Procedure defined (ISIN join); neither file opened, schema-gap caveat unresolved |
| B3-03 NIFTY 500 benchmark | Upstox Developer API | Unknown instrument_key (not found in developer docs) | NO | NO | Exact instrument_key never confirmed; must be looked up via Search Instruments API at acquisition time |
| B3-04 sector mapping | NSE Indices Ltd. | Industry Classification Guideline (methodology only); full mapping is subscription/request-only | PARTIAL | NO | Full taxonomy mapping not publicly downloadable; governance decision needed on which tier/source satisfies D-B3-04 |
| B3-07 trading calendar | NSE India | nseindia.com/resources/exchange-communication-holidays | YES | PARTIAL | No confirmed structured export; page-based extraction procedure still needed |
| B3-05 equity OHLC capability | Upstox Developer API | V3 historical-candle endpoint (generic per instrument_key) | PARTIAL | PARTIAL | Mechanism confirmed via this repo's own prior integration; never called for an equity symbol |
| B3-06 equity volume capability | Upstox Developer API | Same endpoint, `volume` field confirmed in row shape | PARTIAL | PARTIAL | Same as B3-05 |
| B3-08 Upstox vendor authority | Human decision (D-B3-02) | N/A — governance, not a technical source | YES | YES | None (governance-resolved; technical completeness tracked separately above) |

## 10. Remaining Blockers

1. B3-03 — No confirmed Upstox `instrument_key` for the NIFTY 500
   benchmark; nothing further can proceed on the Relative Strength
   component (history availability, lookback sufficiency) until this is
   looked up.
2. B3-04 — NSE Indices' full sector taxonomy is not publicly
   downloadable; a human decision is needed on whether the (unconfirmed)
   "Industry" column bundled in the constituent CSV is an acceptable
   substitute for D-B3-04's "authoritative NSE/Nifty Indices
   classification source," or whether the subscription-based full
   taxonomy must be obtained instead.
3. B3-01/B3-02 — Neither the constituent CSV nor the Upstox instrument
   master has actually been opened; their documented schemas (ISIN,
   Industry, ISIN-based join) are the basis for the mapping procedure in
   Section 4 but are unverified against the real files.
4. B3-01 — Point-in-time historical constituent-list availability (for
   reproducing a past scan date, not just "today") is unconfirmed.
5. B3-07 — No confirmed structured/machine-readable export of NSE's
   holiday calendar; a page-based extraction procedure is still
   required.
6. B3-02 (schema caveat) — A community-reported gap (missing
   `trading_symbol` in some published Upstox instrument records) has not
   been independently confirmed or ruled out, and could affect the
   mapping procedure's reliability if real.

## 11. Data Acquisition Gate

Per Phase 9's eight conditions:

1. Authoritative NIFTY 500 constituent source identified — YES (source
   named and current-list reproducibility documented; file content and
   historical-list availability still unconfirmed)
2. Deterministic constituent → Upstox mapping established — PARTIAL
   (procedure defined, not exercised against real files)
3. Exact NIFTY 500 benchmark instrument established — NO
4. Authoritative sector mapping source established — PARTIAL (framework
   and publisher named; full public mapping not available; governance
   decision pending)
5. Authoritative trading-calendar source established — PARTIAL (source
   named; structured extraction mechanism unconfirmed)
6. Upstox daily OHLC capability verified — PARTIAL (mechanism confirmed
   in principle, never exercised for equities)
7. Upstox daily volume capability verified — PARTIAL (same basis as 6)
8. No unresolved source/governance contradiction remains — YES (no
   contradiction found among the human decisions, the B1 exception, or
   this task's findings)

Conditions 1 and 8 are the only ones that reach a clean YES; the rest are
PARTIAL or NO. Per Phase 9's rule, ALL eight must pass for the gate to
open.

**DATA ACQUISITION GATE = BLOCKED.**

## 12. Explicit Non-Actions

Data acquisition: NO. NIFTY 500 download: NO. 500-stock OHLCV download:
NO. Benchmark data download: NO. Sector mapping download: NO. Database
population: NO. Source-code implementation: NO. Scoring implementation:
NO. Scanner implementation: NO. Dashboard modification: NO.
Trading-engine modification: NO. OMS modification: NO. B2 modification:
NO. `config/symbols.py` modification: NO. Credentials: NO. Broker
orders: NO. Pytest: NOT RUN. Application execution: NOT RUN. Live
trading: NO. `__pycache__` cleanup: NOT ATTEMPTED. Git history
modification: NO.

## 13. Final Adjudication

**B3 SOURCE VERIFICATION INCOMPLETE**
**DATA ACQUISITION GATE = BLOCKED**

This task substantially advanced source identification relative to the
two prior B3 tasks: the NIFTY 500 universe publisher and download
mechanism, the Upstox instrument-mapping mechanism (including a proposed
ISIN-based deterministic join procedure), the NSE sector-classification
framework and publisher, and the NSE trading-holiday source are all now
named with citations, where before several were entirely unidentified.
None of these is yet a closed, verified, exercised end-to-end mechanism:
the NIFTY 500 benchmark's exact Upstox instrument_key remains unfound;
NSE's full sector taxonomy is not publicly downloadable, raising a new
governance question rather than a technical one; and every
mapping/extraction procedure described here is a documented-but-untested
plan, not a confirmed result, because no file was actually opened,
downloaded, or persisted during this task, as instructed. The data
acquisition gate accordingly remains BLOCKED.

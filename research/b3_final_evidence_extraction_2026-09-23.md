# B3 FINAL EVIDENCE EXTRACTION & MAPPING VERIFICATION — 2026-09-23

Controlled, in-memory verification task. This task attempted to move from
documented mechanisms to actually-inspected artifact evidence. That
attempt is reported honestly below: most direct-retrieval attempts were
blocked by this environment's own network egress policy before any file
bytes were obtained, in both the cloud sandbox and the user's linked
device. No source dataset — partial or complete — was ever obtained, so
none was stored, copied, or left behind anywhere, in or out of the
repository.

## 1. Preflight

- HEAD: `03ccce95ff47af479d9382723ae91694d39fb6a2` (confirmed unchanged
  from all three prior B3 tasks)
- Branch: `main` (unchanged)
- Pre-existing modified: 136
- Pre-existing staged: 0
- Pre-existing untracked: 133 (matches the immediately prior task's own
  post-audit count exactly — no drift between tasks)

## 2. NIFTY 500 Constituent Evidence

**Retrieval attempts (all reported, none hidden):**

1. `curl` from the cloud sandbox to
   `https://niftyindices.com/IndexConstituent/ind_nifty500list.csv` —
   FAILED: `curl: (56) CONNECT tunnel failed, response 403` (the
   sandbox's own egress proxy rejected the connection before reaching
   the host at all).
2. `curl` from the user's linked device (via `device_bash`) to the same
   URL — FAILED: identical `403 from proxy after CONNECT`. Confirmed
   this is a network-policy rejection, not a site-side block, by testing
   known-reachable control domains (`github.com`, `pypi.org` — both
   returned HTTP 200 from the same shell) against blocked domains
   (`www.nseindia.com`, `niftyindices.com`, `assets.upstox.com`,
   `api.upstox.com`, even plain `google.com` — all rejected identically
   with `connect_rejected (organization policy)`, per the sandbox's own
   proxy-status diagnostic).
3. `WebFetch` (a separate, higher-level fetch path than direct `curl`,
   used successfully in the prior task to read nseindia.com/upstox.com
   HTML pages) against the same CSV URL — FAILED differently: the tool
   returned "[binary data]" and explicitly stated it could not read
   the file as text, meaning even this path did not yield literal,
   inspectable row/column content for this specific file.

**Result: RETRIEVAL NOT POSSIBLE IN THIS ENVIRONMENT.** No row count, no
column list, no duplicate check, no ISIN/Industry field inspection, and
no verification that the current list actually contains 500 rows could
be performed, because no bytes of the file were ever obtained by any
available method. Per this task's own instruction, this is reported as
BLOCKED rather than inferred from the previous task's search-snippet-based
description (which remains unverified, third-party-sourced information,
now explicitly re-labeled as such rather than escalated to "verified").

**B3-01 = BLOCKED (retrieval not possible in this environment).** This is
a different, narrower finding than the prior task's "source identified":
the organization/publisher and URL identity remain correctly identified
(NSE Indices; the URL pattern is consistent with NSE Indices' other
published index constituent files), but the artifact itself could not be
opened from within this session, on either available compute surface.

## 3. Upstox Instrument-Master Evidence

**Retrieval attempts:**

1. `curl` (cloud sandbox and device, both) to
   `https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz` —
   FAILED identically to Section 2: `403 from proxy after CONNECT` /
   `connect_rejected (organization policy)` on both surfaces.
2. `curl` to `https://api.upstox.com` (base host, no specific endpoint
   called, no credentials used) — FAILED identically, confirming the
   entire `upstox.com`/`upstox` domain family is not reachable from
   either compute surface in this session, independent of authentication.

**What WAS obtained (via `WebFetch` against Upstox's own developer
documentation pages, which — unlike the raw instrument file — rendered
as readable HTML/text through that path):**

- Upstox, "Instruments" documentation,
  https://upstox.com/developer/api-documentation/instruments/, accessed
  2026-09-23. A verbatim NSE-equity example record was returned by the
  fetch:
  ```json
  {
    "segment": "NSE_EQ",
    "name": "JOCIL LIMITED",
    "exchange": "NSE",
    "isin": "INE839G01010",
    "instrument_type": "EQ",
    "instrument_key": "NSE_EQ|INE839G01010",
    "lot_size": 1,
    "freeze_quantity": 100000.0,
    "exchange_token": "16927",
    "tick_size": 5.0,
    "trading_symbol": "JOCIL",
    "short_name": "JOCIL",
    "security_type": "NORMAL"
  }
  ```
  and a verbatim index example record:
  ```json
  {
    "segment": "BSE_INDEX",
    "name": "AUTO",
    "exchange": "BSE",
    "instrument_type": "INDEX",
    "instrument_key": "BSE_INDEX|AUTO",
    "exchange_token": "13",
    "trading_symbol": "AUTO"
  }
  ```
  This is genuine, documented, verbatim evidence of the field set and of
  the `instrument_key` NAMING PATTERN — `NSE_EQ|<ISIN>` for NSE equities,
  `<SEGMENT>|<name>` for indices — but it is a single worked
  documentation example each, not a record pulled from the live
  instrument master, and not proof that every one of ~500+ real
  constituents follows the pattern without exception.

**Answers to Phase 2's ten questions, qualified accordingly:**

1. ISIN present — YES, per the documented example field `isin`.
2. Trading symbol present — YES, per the documented example field
   `trading_symbol`.
3. `instrument_key` present — YES, documented as the recommended unique
   identifier.
4. Exchange identifiable — YES (`exchange: "NSE"`).
5. NSE equity segment identifiable — YES (`segment: "NSE_EQ"`).
6. Instrument type identifiable — YES (`instrument_type: "EQ"`).
7. Duplicate ISINs present — NOT DETERMINABLE (no bulk file inspected).
8. Duplicate trading symbols present — NOT DETERMINABLE (same reason).
9. Records with missing identity fields — NOT DETERMINABLE (same
   reason; the one community report cited in the prior task, of
   sometimes-missing `trading_symbol` values, remains unconfirmed
   either way).
10. Can an NSE-equity instrument be uniquely selected — PLAUSIBLE ONLY:
    the documented example shows `instrument_key = "NSE_EQ|" + isin`,
    which would be unique by construction if ISIN is unique per
    constituent (a reasonable assumption — ISIN is designed to be
    globally unique per security) — but this was not verified against
    real bulk data.

**B3-02 = MECHANISM PATTERN DOCUMENTED (ONE WORKED EXAMPLE), BULK DATA
NOT INSPECTED — REMAINS UNVERIFIED AS A COMPLETE MAPPING.** A concrete,
new, useful fact this task adds beyond the prior one: if a constituent's
ISIN is known, its Upstox equity `instrument_key` can very likely be
constructed directly as `NSE_EQ|<ISIN>` without needing to search or
download anything further — this is a plausible, documented shortcut,
not a substitute for actually confirming it against real records.

## 4. NIFTY 500 → Upstox Mapping Test

**Result: NOT PERFORMED.** Phase 3 requires actual constituent data
(Section 2) and actual instrument-master data (Section 3) as inputs.
Neither was obtained. No in-memory join was computed, because there was
nothing real to join — computing one from search-snippet descriptions
would mean fabricating match/unmatch counts against data never actually
seen, which this task's own rules and this repository's whole governance
posture (throughout every prior B2/B3 task) explicitly forbid.

Total NIFTY 500 constituents: NOT DETERMINED (source unopened).
Successfully matched: 0 (nothing attempted against real data).
Unmatched: NOT DETERMINED.
Multiple matches: NOT DETERMINED.
Missing identity fields: NOT DETERMINED.
Duplicate candidates: NOT DETERMINED.
Ambiguous mappings: NOT DETERMINED.
Invalid/non-equity matches: NOT DETERMINED.

**B3-02 (mapping test specifically) = BLOCKED (inputs unavailable).**

## 5. NIFTY 500 Benchmark Evidence

**Retrieval attempts:** identical failures to Sections 2-3 for any
Upstox instrument-master or live API lookup of an NSE_INDEX record named
"Nifty 500" — the relevant hosts (`assets.upstox.com`, `api.upstox.com`)
were unreachable from both compute surfaces in this session.

**What is and is not established:**

- This repository already confirms, independently of this task, the
  NIFTY 50 index's real, exercised instrument_key:
  `"NSE_INDEX|Nifty 50"` (from `config/symbols.py`, sourced from
  `core/upstox_data.py`'s actual `get_option_chain()` default).
- Section 3's newly-obtained documentation example confirms the general
  index key format is `<SEGMENT>|<display name>` (shown there for a BSE
  index, consistent with the NIFTY 50 NSE example already in this repo).
- Applying that same, now twice-confirmed pattern would suggest
  `"NSE_INDEX|Nifty 500"` as the likely benchmark key. This task
  explicitly declines to record that as verified: it is a pattern
  extrapolation, not an actual record pulled from Upstox's instrument
  master or Search Instruments API for that specific index, and no
  attempt to query the live Search Instruments API was possible (host
  unreachable).

**B3-03 = BLOCKED.** Exact name: NIFTY 500 (NSE Indices' official name,
confirmed in the prior task). Exchange: NSE (by extension of the
established pattern, not independently confirmed for this index).
Segment: presumed `NSE_INDEX` (pattern-consistent, not confirmed).
Instrument type: presumed `INDEX` (pattern-consistent, not confirmed).
Trading symbol: unknown. `instrument_key`: NOT ESTABLISHED — explicitly
not guessed, per this task's own instruction. Evidence source: none
beyond pattern inference from a different index's documented example.

## 6. Sector / Industry Evidence

**Retrieval attempts:** the NIFTY 500 constituent CSV (which the prior
task's secondary, third-party source reported as containing an
`Industry` column) could not be opened for the same reason as Section 2
— `niftyindices.com` unreachable from both compute surfaces, and
`WebFetch` returned "[binary data]" for that specific file.

**Result: FIELD VALUES NOT INSPECTED.** None of the following could be
determined from actual data: exact field name as it appears in the real
header row, number of unique values, sample values, per-row coverage
(whether every constituent has a value), or whether NSE Indices'
publisher-side documentation explicitly labels this column as a formal
"sector" (as opposed to an informal display grouping).

Per this task's explicit rule:

**PUBLIC INDUSTRY FIELD EXISTS — SECTOR EQUIVALENCE NOT ESTABLISHED.**
(Even this much is carried over from the prior task's secondary,
non-primary source — a Medium article's description of the CSV's
columns — not from this task's own inspection, since this task could not
open the file either. The prior task's own separately-confirmed primary
finding stands unchanged: NSE Indices' official page
(nseindia.com/static/products-services/industry-classification) states
outright that the full 4-tier classification mapping is
subscription/request-only, not a public download — so even a confirmed
CSV `Industry` column would be a different, shallower artifact than the
formal taxonomy D-B3-04 names, and the governance question raised in the
prior task — which of the two counts as satisfying D-B3-04 — remains
open and requires a human decision, not further technical work.)

**B3-04 = BLOCKED**, for two independent reasons: (a) the free/bundled
`Industry` field's actual content is unverified (retrieval blocked), and
(b) even if verified, whether it satisfies "an authoritative NSE/Nifty
Indices classification source" per D-B3-04, versus requiring the
subscription-only full taxonomy, is an unresolved governance question
this task cannot answer on its own.

## 7. NSE Trading-Calendar Evidence

**Retrieval attempts:** `curl` to `www.nseindia.com` from both compute
surfaces failed identically to Sections 2-3 (`403`/`connect_rejected`).
`WebFetch` against
`https://www.nseindia.com/resources/exchange-communication-holidays`,
however, DID succeed in returning readable page content (as it had in
the prior task) — this page apparently renders through the `WebFetch`
path differently than the blocked CSV/JSON files did.

**Actual evidence obtained (genuinely, not paraphrased from a snippet):**
the fetch explicitly reported that the page's static HTML does NOT
contain the actual holiday date list for a selected year — that list
"appears to load dynamically via JavaScript or an API call after
selecting the year and product type" — and that only ONE specific date
was present verbatim in the fetched content: "November 08, 2026, shall
be a trading holiday on account of Diwali Laxmi Pujan." This is a
genuine, narrow, honestly-scoped piece of evidence: one confirmed
special-session date, and an explicit confirmation that the full
programmatic calendar is not obtainable through this page's static
content.

**Verification answers:**

1. Official calendar source — VERIFIED (page reached, confirmed to be
   NSE's own Exchange Communications resource).
2. Equity-market applicability — page offers a Capital Market segment
   selector; not independently re-confirmed this task beyond the prior
   task's finding.
3. Holiday dates (full list) — NOT OBTAINED; dynamically loaded, not in
   static content.
4. One special session date — CONFIRMED VERBATIM (Nov 8, 2026, Diwali
   Laxmi Pujan).
5. Structured/machine-readable representation — NOT FOUND; the page
   itself is JS-driven, and no separate API/file endpoint was
   discovered or reachable in this task.
6. Deterministic 252-session reconstruction — NOT ESTABLISHED. Neither
   the full holiday list nor a structured export was obtained.

**B3-07 = BLOCKED.** Source identity remains confirmed (unchanged from
the prior task); a deterministic, reproducible extraction mechanism is
still not established, and this task could not close that gap because
the actual calendar data — unlike the page shell around it — was not
reachable by any method available in this session.

## 8. Upstox OHLC / Volume Capability

This section required no new external retrieval: it rests entirely on
this repository's own already-exercised code
(`core/historical_data.py`), which independently of this task's network
constraints already documents and has previously (per its own comments)
confirmed the V3 historical-candle endpoint's contract — generic per
`instrument_key`, `unit=days`/`interval=1` valid for daily candles,
response rows including `open, high, low, close, volume, oi`. This
finding is unchanged from the prior two B3 tasks and was not
re-verified against a live call in this task (calling the live API was
explicitly out of scope and would also have required the same blocked
`api.upstox.com` host).

Equity OHLC: PARTIAL (mechanism documented and previously exercised in
this repo for the NIFTY 50 index; never exercised for any equity symbol;
this task added no new evidence either way).
Equity volume: PARTIAL (same basis).

## 9. Evidence Matrix

| Requirement | Actual Evidence | Result | Remaining Issue |
|---|---|---|---|
| B3-01 NIFTY 500 universe | None obtained — all retrieval attempts (curl ×2 surfaces, WebFetch) failed before any file bytes were read | BLOCKED | Retrieval not possible in this environment; source identity unchanged from prior task |
| B3-02 Upstox mapping | One verbatim documentation example (`NSE_EQ\|<ISIN>` pattern); no bulk record inspected | PARTIALLY VERIFIED | Pattern documented, not confirmed against real records; bulk file unreachable |
| B3-03 NIFTY 500 benchmark | Pattern inference only (from a different index's documented example + this repo's own NIFTY 50 key); no direct evidence for NIFTY 500 itself | BLOCKED | Exact instrument_key not established; live lookup unreachable |
| B3-04 sector mapping | None newly obtained; prior task's governance finding (full taxonomy is subscription-only) stands | BLOCKED | Retrieval blocked; also an open governance question independent of retrieval |
| B3-07 trading calendar | One verbatim confirmed date (Nov 8, 2026 special session); full list confirmed to be dynamically loaded, not statically available | BLOCKED | Full calendar and structured export both unobtained |
| B3-05 equity OHLC capability | Repository's own pre-existing, previously-exercised code/documentation (unchanged by this task) | PARTIALLY VERIFIED | Never exercised for equities; live host unreachable this task |
| B3-06 equity volume capability | Same basis as B3-05 | PARTIALLY VERIFIED | Same as B3-05 |

## 10. Remaining Blockers

1. This session's network egress policy blocks every host that would be
   needed to actually inspect the NIFTY 500 constituent file, the
   Upstox instrument master, and the Upstox live API
   (`niftyindices.com`, `assets.upstox.com`, `api.upstox.com`, and even
   `www.nseindia.com` for direct `curl`) — confirmed by testing against
   known-reachable control domains from the same shells. This is an
   environment/infrastructure constraint, not a data-availability
   question, and it blocks essentially all of Phases 1-4 regardless of
   whether the underlying sources are otherwise good.
2. B3-03 — No confirmed NIFTY 500 benchmark `instrument_key`; only a
   plausible, undconfirmed pattern extrapolation exists.
3. B3-04 — Full NSE Indices sector taxonomy remains subscription-only
   per the prior task's confirmed finding; whether the (still unopened)
   CSV `Industry` column is an acceptable substitute is an open
   governance question, not resolvable by more retrieval attempts alone.
4. B3-07 — NSE's holiday calendar is confirmed to be dynamically loaded
   (JS/API-driven); no static or structured export was found or
   reachable, so no deterministic 252-session extraction method is
   established.
5. B3-01/B3-02 mapping test — Entirely unexecuted; both required inputs
   are unobtained.

## 11. Data Acquisition Gate

Per Phase 9's rule (all seven of B3-01/02/03/04/07/05/06 must equal
VERIFIED):

- B3-01: BLOCKED
- B3-02: PARTIALLY VERIFIED
- B3-03: BLOCKED
- B3-04: BLOCKED
- B3-07: BLOCKED
- B3-05: PARTIALLY VERIFIED
- B3-06: PARTIALLY VERIFIED

None reach a clean VERIFIED; several are outright BLOCKED.

**DATA ACQUISITION GATE = BLOCKED.**

## 12. Temporary Artifacts

One empty temporary directory was created for this task:
`/tmp/b3evidence` on the user's linked device (outside any connected
folder, outside the repository, never staged or committed). No file was
ever successfully written into it — every retrieval into it failed
before any bytes arrived (confirmed: `ls -la` showed it empty
immediately before removal). It was removed with `rmdir` at the end of
this task's retrieval attempts, and its absence was re-confirmed
afterward. No cloud-sandbox scratch file was created either (the
cloud-side `curl` attempt also failed with zero bytes downloaded, and no
file was written as a result). Nothing entered the repository at any
point.

## 13. Explicit Non-Actions

NIFTY 500 dataset permanently stored: NO. 500-stock OHLCV acquired: NO.
Benchmark history acquired: NO. Sector mapping stored: NO. Calendar file
created: NO. Database populated: NO. Source code modified: NO. Scoring
modified: NO. Dashboard modified: NO. Trading engine modified: NO. OMS
modified: NO. B2 modified: NO. Pytest: NOT RUN. Application: NOT RUN.
Live trading: NO. Git staging: NO. Git commit: NO. Bytecode cleanup: NOT
ATTEMPTED.

## 14. Final Adjudication

**B3 SOURCE VERIFICATION INCOMPLETE**
**DATA ACQUISITION GATE = BLOCKED**

This task's core objective — turning "source identified" and "mechanism
documented" into "actual evidence inspected" — was only partially
achievable, and the honest result is a narrower one than either prior
task reached: this session's own network egress policy prevents direct
retrieval of every actual data artifact this investigation needed
(the NIFTY 500 constituent file, the Upstox instrument master, and any
live Upstox API endpoint), on both available compute surfaces, verified
against working control domains rather than assumed. The one indirect
fetch path available (`WebFetch`) could reach some HTML documentation
pages — yielding two genuinely new, verbatim pieces of evidence (an
Upstox equity instrument_key example following the `NSE_EQ|<ISIN>`
pattern, and one confirmed real holiday date) — but could not read the
CSV or JSON data files themselves. No dataset, partial or complete, was
obtained, stored, or left behind anywhere. The data acquisition gate
remains BLOCKED, and closing the remaining gaps requires either a
different network path than is available in this session, or a
follow-on task run from an environment where these hosts are reachable.

# B3-01 THROUGH B3-07 FINAL RESOLUTION — 2026-09-23

## 1. Preflight

Baseline substitution instructed by the user (previous task's recorded
HEAD, `03ccce95ff47af479d9382723ae91694d39fb6a2`, is no longer current).

- BASELINE HEAD: `ee4bfb2cd92337f272ef13c35e5150c029b71cf3` (confirmed via
  fresh `git rev-parse HEAD` at the start of this task)
- BASELINE BRANCH: `main` (confirmed via fresh `git branch --show-current`)
- BASELINE MODIFIED COUNT: 136
- BASELINE STAGED COUNT: 0
- BASELINE UNTRACKED COUNT: 132

All 136 modified and 132 untracked entries are pre-existing working-tree
state (includes `equity_intel/`, prior `research/b3_*` audit reports,
`core/regime_logger.py`, `strategies/nifty_momentum_scalper.py`, and
others) and are treated as baseline, not as deltas produced by this task.
No repository state (tracked or untracked) was modified, staged, cleaned,
restored, or committed by this task.

## 2. B3-01 — NIFTY 500 Universe

**Repository evidence (step 1 of the access hierarchy):** No constituent
file, cached copy, or snapshot of the NIFTY 500 list exists anywhere in
the repository. Targeted search of `core/`, `equity_intel/`, `config/`,
`data/`, `research/`, `docs/` for `*nifty500*`, `*.gz`, `*instrument*master*`,
`*complete.json*` returned no matches. `config/symbols.py` contains only a
hand-maintained, partial NIFTY 50-stocks dict (yfinance-style `.NS`
symbols, no ISIN, most `enabled: False`) — not a NIFTY 500 universe.

**Locally cached artifact (step 2):** None found.

**Authoritative public web source (step 3):** Attempted direct retrieval
of `https://niftyindices.com/IndexConstituent/ind_nifty500list.csv` by
two methods this task actually ran itself:
- `curl` from the linked device's shell — **FAILED**: `403 from proxy
  after CONNECT`. Control-domain test in the same shell confirms this is
  an organization egress-policy rejection, not a site-side block:
  `github.com` returned `200`; `niftyindices.com`, `www.nseindia.com`,
  and `assets.upstox.com` each returned `000`/`curl: (56) Received HTTP
  code 403 from proxy after CONNECT`.
- `WebFetch` against the same CSV URL — **FAILED**: the tool reported the
  content as unreadable binary data, yielding no row/column content.

**Step 4/5:** No already-available authoritative artifact can establish
this requirement — none exists in the repository, and the live source
could not be opened by any method available in this session.

Prior sessions' `research/b3_data_source_readiness_audit_2026-09-22.md`
and `research/b3_final_evidence_extraction_2026-09-23.md` record the same
outcome (publisher/URL identity correctly identified, file never opened)
across three earlier attempts. This task reproduces that same environment
constraint via its own fresh calls rather than merely citing the prior
finding.

**B3-01 = BLOCKED.** Publisher and URL pattern are correctly identified
(NSE Indices; `ind_nifty500list.csv`) but the artifact itself was never
opened, so constituent count, field names (Symbol/Company Name/ISIN/
Industry), and reproducibility remain unverified. No constituent count is
asserted anywhere in this report.

## 3. B3-02 — Upstox Instrument Mapping

**Repository evidence:** `config/symbols.py` stores no ISIN and no
per-stock `upstox_instrument_key` for any equity — only index-level keys
(see Section 4). There is no equity ISIN→instrument_key table anywhere in
the repo to inspect or test against.

**Locally cached artifact:** None (no Upstox instrument-master file
present anywhere in the repository, confirmed by the same search as
Section 2).

**Authoritative public web source:** `curl` to
`https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz`
from the linked device — **FAILED** identically (`403 from proxy after
CONNECT`). `WebFetch` against Upstox's own instruments documentation page
(`https://upstox.com/developer/api-documentation/instruments/`) **did**
render as text and returned this verbatim worked example:

```json
{"segment": "NSE_EQ", "name": "JOCIL LIMITED", "isin": "INE839G01010",
 "instrument_type": "EQ", "instrument_key": "NSE_EQ|INE839G01010",
 "trading_symbol": "JOCIL"}
```

confirming the field set (`isin`, `trading_symbol`, `instrument_key`,
`exchange`, `segment`, `instrument_type`) and the `instrument_key =
"NSE_EQ|<ISIN>"` naming convention — but this is one documentation
example, not a bulk instrument-master file, and the page did not give the
actual download URL for the complete/NSE instrument file.

**In-memory mapping test:** **NOT PERFORMED.** No actual NIFTY 500
constituent data (Section 2, BLOCKED) and no actual Upstox
instrument-master data (bulk file unreachable) were obtained, so there is
nothing real to join. Per this task's no-fabrication rule, matched/
unmatched/duplicate/ambiguous counts are not reported, because computing
them would require data never actually seen.

**B3-02 = BLOCKED.** A plausible, documented construction pattern
(`NSE_EQ|<ISIN>`) exists from one verbatim example, but a deterministic
mapping for all NIFTY 500 constituents was not proven against real bulk
data, and the required in-memory mapping test could not run at all.

## 4. B3-03 — NIFTY 500 Benchmark

**Repository evidence:** `config/symbols.py` line 36 has a real,
previously-exercised index key: `"upstox_instrument_key": "NSE_INDEX|Nifty
50"` (NIFTY 50, not NIFTY 500). No NIFTY 500 index entry exists anywhere
in the repo.

**Public web source:** Upstox's own instruments-documentation page (same
fetch as Section 3) gives only a different index's worked example —
`"instrument_key": "BSE_INDEX|AUTO"` — confirming the general
`<SEGMENT>|<display name>` index-key pattern but not a NIFTY 500-specific
record. `assets.upstox.com` / `api.upstox.com` (where a Search Instruments
API call could confirm the exact key) were unreachable (`403 from proxy
after CONNECT`, same control-domain test as Section 2). Web search
(`Upstox instrument_key "NIFTY 500" NSE_INDEX`) surfaced only consumer
pages (upstox.com's own retail index page, Wikipedia, Google Finance,
TradingView) — none of these state a formal `instrument_key`, and per
this task's rule against substituting consumer sites for authoritative
API evidence, none is used as such here even as supporting evidence.

Applying the twice-confirmed pattern (`NSE_INDEX|Nifty 50` in this repo +
`BSE_INDEX|AUTO` in Upstox's own docs) would suggest `"NSE_INDEX|Nifty
500"` — this is explicitly **not** recorded as verified, per this task's
own instruction not to infer the key from naming conventions.

**B3-03 = BLOCKED.** Index identity (NIFTY 500, NSE, official NSE Indices
name) is not in question; the exact Upstox `instrument_key` is not
established by any evidence actually inspected in this task.

## 5. B3-04 — Sector Mapping

**Repository evidence:** No sector/industry classification file or table
exists anywhere in the repository (same search as Section 2). No code
path in `equity_intel/` currently consumes a sector field — the
`classification/` module has interfaces only (`interfaces.py`), no
implementation and no data.

**Public web source:** The `ind_nifty500list.csv` file that a prior
task's third-party (Medium-article) source described as having an
`Industry` column could not be opened this task either — same failure as
Section 2 (`403` on `curl`, unreadable binary via `WebFetch`), so its
actual header row, field name, and coverage were not inspected. NSE
Indices' industry-classification page
(`nseindia.com/static/products-services/industry-classification`) was not
independently re-fetched this task (host in the same blocked family
confirmed by the control-domain test); no new evidence on the
subscription-only-taxonomy question was obtained.

**CRITICAL rule applied:** Industry is not treated as Sector. Since the
CSV `Industry` column itself was never opened by this task, there is no
evidence — from this task — to even evaluate that equivalence question
against, let alone resolve it.

**B3-04 = BLOCKED.** No sector/industry field was inspected. Whether a
free `Industry` column (if one exists and were opened) would satisfy the
"authoritative NSE/Nifty Indices classification" requirement, versus
needing NSE's subscription/request-only full taxonomy, remains an open
question this task cannot resolve without first opening the source file.

## 6. B3-05 — Equity OHLC Readiness

**Repository evidence (genuine, inspected directly):**
`core/historical_data.py` documents and calls Upstox's V3 Historical
Candle endpoint:
`GET https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}`,
with `unit` including `"days"` and response rows parsed into
`CANDLE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume",
"oi"]` (`_rows_to_dataframe`, line 149 area). The endpoint is generic per
`instrument_key` — nothing in the code path restricts it to indices — but
this repo's actual, exercised usage is 100% index-only:
`NIFTY_INSTRUMENT_KEY = SYMBOLS["NIFTY"]["upstox_instrument_key"]`
(`"NSE_INDEX|Nifty 50"`), used for 1/5/15-minute intraday candles, not
daily, and never for any equity instrument.

The module's own header comment and `core/test_historical_data.py`'s
docstring both state explicitly, in the code itself: *"this module needs
a REAL Upstox access token and REAL network access to actually fetch
anything. It cannot be exercised end-to-end in a sandbox with no Upstox
account and no egress to api.upstox.com."* All existing tests use a fake
`fetch_fn` and never contact `api.upstox.com`. This session's own
control-domain test (Section 2) confirms `api.upstox.com` is still
unreachable from both compute surfaces now.

**B3-05 = BLOCKED.** The endpoint contract (fields, generic per
instrument_key, `unit="days"` valid) is documented in Upstox's own API
shape and already coded against in this repo, but capability against a
real equity instrument, for daily bars, over a 252-session window, has
never actually been exercised or confirmed live — only intraday index
candles have, and even that has never been confirmed against the live
API in this environment. "Documented + coded" is not the same as
"verified," and this task's evidence standard forbids "should"/"appears
to" as the basis for VERIFIED.

## 7. B3-06 — Equity Volume Readiness

**Repository evidence (genuine, inspected directly):**
`core/historical_data.py::candles_to_bars` docstring and inline comment
state, as a fact already observed by this repo's own historical usage:
*"the NIFTY index's historical candles carry volume=0 in every row this
repo has ever fetched."* The function passes volume through unmodified
and explicitly does not fabricate or substitute a different value.

This is directly relevant to this task's own warning not to use NIFTY 50
index volume as evidence of equity volume: this repo's own evidence shows
the *index* candle volume field is populated but always zero — it neither
confirms nor denies what equity-instrument volume looks like, and cannot
be extrapolated to equities regardless.

**No equity volume field was ever inspected** — no equity instrument has
been queried against this endpoint by this repo, live or cached, and
`api.upstox.com` remains unreachable this task (same control-domain test
as Section 2/6).

**B3-06 = BLOCKED.** Volume field exists in the documented response shape
and is passed through by this repo's own parsing code, but its real
semantics for an equity instrument (non-zero vs. always-zero, tick vs.
aggregated) have not been observed anywhere, and this repo's only actual
volume observation (index, always 0) is explicitly not usable as equity
evidence per this task's own rule.

## 8. B3-07 — 252-Trading-Session Calendar

**Public web source:** `WebFetch` against
`https://www.nseindia.com/resources/exchange-communication-holidays`
rendered readable page content (unlike the blocked CSV/JSON paths) and
returned one verbatim date present in the static content: *"November 08,
2026, shall be a trading holiday on account of Diwali Laxmi Pujan."* The
page's own text states the full holiday list for a selected year/product
"loads dynamically via JavaScript or an API call after selecting the year
and product type" — i.e., the complete Capital Market 2026 holiday list
is not present in this page's static HTML and was not obtained.

A web search for a structured/complete 2026 NSE holiday list (`NSE India
trading holidays 2026 list capital market`) returned only consumer
finance sites (Groww, Zerodha, Kotak, Bajaj AMC, Tata Mutual Fund,
Smallcase, Anand Rathi, ProStocks, Aditya Trading) — none of these are
NSE/Nifty Indices' own official source, so per this task's rule against
substituting consumer sites for authoritative evidence where the
requirement specifically needs official source verification, none is
used to establish the calendar (they could only ever be labeled
THIRD-PARTY supporting evidence, and this task does not promote them).

**Repository evidence:** No calendar file, holiday list, or session-count
artifact exists anywhere in the repository.

**B3-07 = BLOCKED.** Official source identity is confirmed (NSE's own
Exchange Communications holidays resource) and one real holiday date is
confirmed verbatim, but no full, structured, or reproducible 2026
Capital Market holiday list was obtained by any method run in this task,
so a deterministic 252-completed-trading-session sequence cannot be
constructed from evidence actually inspected here.

## 9. Evidence Matrix

| ID | Requirement | Evidence | Result | Remaining Gap |
|----|-------------|----------|--------|---------------|
| B3-01 | NIFTY 500 universe | No repo artifact; `curl`/`WebFetch` to `niftyindices.com` both failed (proxy 403 / unreadable binary) | BLOCKED | Constituent file never opened; count/fields/ISIN/Industry unverified |
| B3-02 | Upstox mapping | No repo ISIN/instrument_key table; one verbatim Upstox doc example (`NSE_EQ\|<ISIN>` pattern); bulk instrument master unreachable | BLOCKED | No mapping test run — both real inputs (constituents, instrument master) unobtained |
| B3-03 | NIFTY 500 benchmark | Repo has NIFTY 50 key (`NSE_INDEX\|Nifty 50`) only; Upstox docs give a different index's example (`BSE_INDEX\|AUTO`); no NIFTY 500-specific record found | BLOCKED | Exact `instrument_key` for NIFTY 500 not established; not guessed |
| B3-04 | Sector mapping | No repo sector/industry file; CSV `Industry` column never opened this task | BLOCKED | Source file unopened; Industry-vs-Sector governance question unresolved |
| B3-05 | Equity OHLC | Repo documents/codes V3 candle endpoint incl. `unit="days"`; only ever exercised for NIFTY index intraday, never equities, never live | BLOCKED | No live or equity-instrument exercise of the endpoint |
| B3-06 | Equity volume | Repo's own code confirms NIFTY index volume is always 0 in every fetch to date; no equity volume ever observed | BLOCKED | No equity volume observation exists; index-volume evidence explicitly not usable per task rule |
| B3-07 | 252-session calendar | Official NSE holidays page reached; one verbatim 2026 date confirmed; full list confirmed to load dynamically (not in static content) | BLOCKED | Full 2026 Capital Market holiday list not obtained; no deterministic session sequence constructible |

## 10. Remaining Blockers

1. This session's organization egress policy rejects `niftyindices.com`,
   `www.nseindia.com` (direct `curl`), `assets.upstox.com`, and
   `api.upstox.com` on both available compute surfaces (`403 from proxy
   after CONNECT`), confirmed against working control domains
   (`github.com` → 200) in this same task run. This blocks direct
   retrieval of the NIFTY 500 constituent file, the Upstox instrument
   master, and any live Upstox API call.
2. `WebFetch` can reach some HTML documentation/informational pages
   (Upstox docs, the NSE holidays page shell) but cannot read the CSV/JSON
   data files themselves, and the NSE holidays page's actual date list is
   client-side/dynamic and not present in fetched static content.
3. B3-04's Industry-vs-Sector equivalence question cannot be resolved
   without first opening the constituent CSV — a governance question that
   sits behind, not instead of, the retrieval blocker.
4. No equity-instrument evidence (OHLC or volume) has ever been obtained
   by this repository, live or cached — B3-05/B3-06 rest entirely on a
   generic, documented endpoint contract and an index-only usage history.

## 11. Data Acquisition Gate

- B3-01: BLOCKED
- B3-02: BLOCKED
- B3-03: BLOCKED
- B3-04: BLOCKED
- B3-05: BLOCKED
- B3-06: BLOCKED
- B3-07: BLOCKED

**DATA ACQUISITION GATE = BLOCKED.**

## 12. Explicit Non-Actions

Permanent NIFTY 500 dataset: NO. 500-stock OHLCV acquired: NO. Benchmark
history acquired: NO. Permanent sector mapping created: NO. Permanent
calendar file created: NO. Database (`equity_intel.db` or other)
populated: NO. Source code modified: NO (scanner, scoring, dashboard,
trading engine, OMS, risk manager, brokers, strategies, `config/
symbols.py`, B2 all untouched). Pytest: NOT RUN. Application: NOT RUN.
Live trading: NO. `__pycache__` cleanup: NOT ATTEMPTED. Git staging: NO.
Git commit: NO.

## 13. Final Adjudication

**B3 SOURCE VERIFICATION INCOMPLETE — DATA ACQUISITION GATE BLOCKED**

Every B3 item remains BLOCKED. This task ran its own fresh retrieval
attempts (not a re-citation of prior tasks' results) via `curl` from the
linked device, `WebFetch`, and `WebSearch`, and independently confirmed
the same organization-level network egress restriction three prior tasks
recorded: the specific hosts required to open the NIFTY 500 constituent
file, the Upstox instrument master, and any live Upstox API endpoint are
rejected by this environment's proxy, verified against a working control
domain in the same shell. Two genuinely new pieces of evidence were
added this task beyond what a repo-only read would give: (1) direct,
first-hand confirmation via this repo's own code (not a prior report's
paraphrase) that `core/historical_data.py` has only ever exercised the
candle endpoint against the NIFTY 50 index, never an equity, and never
live; and (2) direct, first-hand confirmation that this repo's own
observed NIFTY index volume is always zero, which is exactly the trap
this task's B3-06 instructions warn against treating as equity evidence.
No constituent counts, instrument keys, sector mappings, or calendar
dates were fabricated or inferred from naming patterns anywhere in this
report.

---

# ============================================================
# B3-01 THROUGH B3-07 — FINAL RESOLUTION
# ============================================================

B3-01 NIFTY 500 UNIVERSE:
BLOCKED

B3-02 UPSTOX MAPPING:
BLOCKED

B3-03 NIFTY 500 BENCHMARK:
BLOCKED

B3-04 SECTOR MAPPING:
BLOCKED

B3-05 EQUITY OHLC:
BLOCKED

B3-06 EQUITY VOLUME:
BLOCKED

B3-07 252-SESSION CALENDAR:
BLOCKED

DATA ACQUISITION GATE:
BLOCKED

REMAINING BLOCKERS:
1. Organization egress policy blocks `niftyindices.com`, `nseindia.com`
   (direct fetch), `assets.upstox.com`, `api.upstox.com` on both compute
   surfaces — confirmed this task against a working control domain.
2. `WebFetch` reaches some documentation/HTML pages but not the raw
   CSV/JSON data files, or dynamically-loaded page content (NSE holiday
   list).
3. B3-04's Industry-vs-Sector question and B3-05/06's equity-vs-index
   capability gap cannot be closed without the blocked sources.

NON-ACTIONS:
Data acquired: NO
500-stock OHLCV acquired: NO
Database populated: NO
Code modified: NO
Dashboard modified: NO
Trading engine modified: NO
B2 modified: NO
Pytest: NO
Live trading: NO

GIT:
HEAD unchanged: YES
Branch unchanged: YES
Staged files: 0
Commits created: 0

FINAL ADJUDICATION:
B3 SOURCE VERIFICATION INCOMPLETE — DATA ACQUISITION GATE BLOCKED

STOP.

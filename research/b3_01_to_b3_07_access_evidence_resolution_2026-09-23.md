# B3-01 THROUGH B3-07 — ACCESS & EVIDENCE RESOLUTION

## 1. Preflight

- HEAD: `ee4bfb2cd92337f272ef13c35e5150c029b71cf3` (fresh `git rev-parse HEAD`)
- Branch: `main` (fresh `git branch --show-current`)
- Modified count: 136
- Staged count: 0
- Untracked count: 133 (includes the already-existing
  `research/b3_01_to_b3_07_final_resolution_2026-09-23.md`)

**Baseline matched the expected values exactly.** No reset, clean, restore,
checkout, rebase, amend, commit, or stash was performed. No pre-existing
file (tracked or untracked) was modified or deleted.

## 2. Method

**Access paths attempted this task:**
- Direct `curl` from the linked device's shell (`device_bash`) against
  every relevant host, plus a control-domain test.
- Direct `curl` from the cloud sandbox shell, same hosts.
- `WebFetch` against specific documentation/informational URLs.
- `WebSearch` for the exact, current Upstox documentation URLs (since
  `upstox.com/developer/...` pages are JS-templated and don't always list
  literal sub-page URLs in their own body text).
- Inspection of existing, already-present repository code and files
  (`core/historical_data.py`, `config/symbols.py`, `equity_intel/persistence/schema.py`,
  `requirements.txt`, `config/.token_cache.json` metadata only).

**Sources inspected:**
- `niftyindices.com/IndexConstituent/ind_nifty500list.csv`
- `www.nseindia.com`, `archives.nseindia.com`, `nsearchives.nseindia.com`,
  `static.nseindia.com`, `www.nseindia.com/resources/exchange-communication-holidays`
- `assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz`
- `api.upstox.com` (base host)
- `upstox.com/developer/api-documentation/instruments/`
- `upstox.com/developer/api-documentation/instrument-search/`
- `upstox.com/developer/api-documentation/get-market-quote` (404 — wrong
  path, not retried under a different guess)

**Constraints encountered:** identical to the prior resolution task. This
session's organization egress policy rejects CONNECT to
`niftyindices.com`, `nseindia.com` and all tested subdomains
(`www.`, `archives.`, `nsearchives.`, `static.`), `assets.upstox.com`, and
`api.upstox.com`, on both the linked device's shell and the cloud
sandbox shell — confirmed against a working control domain (`github.com`)
in the same shells at the same time. `WebFetch` can render some
`upstox.com/developer/...` HTML documentation pages as text, but cannot
read `.csv`/`.json.gz` binary artifacts (reports them as unreadable
binary), and cannot execute live API calls (it fetches static/rendered
page content, not authenticated API responses).

**Temporary-file policy:** No temporary artifact was created anywhere —
in the repository or outside it — because no retrieval attempt actually
produced any file bytes to hold. Nothing exists to delete or report as
leftover.

## 3. Evidence Matrix

| Item | Requirement | Source | Evidence Actually Obtained | Status | Remaining Gap |
|------|-------------|--------|------------------------------|--------|----------------|
| B3-01 | NIFTY 500 constituent universe | NSE Indices `ind_nifty500list.csv` | None — `curl` (both surfaces) and `WebFetch` both failed to return readable content | BLOCKED | Artifact never opened; no count/fields/ISIN/as-of date observed |
| B3-02 | Upstox equity instrument mapping | Upstox instrument-master / Search Instruments API docs | One verbatim equity doc example (`NSE_EQ\|<ISIN>` pattern) + full Search Instruments API spec (`GET https://api.upstox.com/v2/instruments/search`, params documented) — API itself unreachable | NOT VERIFIED | Documented mechanism, not exercised; no real constituent-to-instrument join performed |
| B3-03 | NIFTY 500 benchmark instrument | Upstox Search Instruments API / instrument master | Confirmed doc example for a *different* index (`NSE_INDEX\|Nifty 50`, `NSE_INDEX\|Nifty 50` verbatim from Search API docs); no NIFTY 500-specific record found anywhere reachable | BLOCKED | Exact `instrument_key` for NIFTY 500 not established; API unreachable to query it |
| B3-04 | Sector mapping | NSE/Nifty Indices classification | None — constituent CSV and NSE industry-classification page both unreachable this task | BLOCKED | Industry-vs-Sector field never inspected; governance question unresolved |
| B3-05 | Equity daily OHLC | Upstox V3 Historical Candle API | Endpoint contract documented and coded in-repo (`unit="days"` valid); repo has only ever exercised it for the NIFTY 50 index, intraday, never live, never for any equity | BLOCKED | No live or equity-instrument exercise performed |
| B3-06 | Equity daily volume | Upstox V3 Historical Candle API | Repo's own code confirms NIFTY index volume is always 0 in every historical fetch to date; this is explicitly NOT used as equity evidence per this task's rule; no equity volume ever observed | BLOCKED | No equity volume observation exists anywhere |
| B3-07 | 252-session trading calendar | NSE Exchange Communications holidays page | Official page reached (`WebFetch`); one verbatim 2026 holiday date obtained; full list confirmed to load dynamically, not present in static content; `archives.nseindia.com` (a plausible structured-data host) also unreachable | BLOCKED | Full 2026 Capital Market holiday list not obtained; no deterministic session sequence constructible |

## 4. Detailed Findings

### B3-01
- **Source:** NSE Indices, `https://niftyindices.com/IndexConstituent/ind_nifty500list.csv`.
- **Access result:** `curl` from the linked device — `403 from proxy after CONNECT`. `curl` from the cloud sandbox — `CONNECT tunnel failed, response 403`. `WebFetch` against the same URL — content reported as unreadable binary, no text/rows returned.
- **Evidence:** None obtained. No repository copy or cache exists either (targeted search of `core/`, `equity_intel/`, `config/`, `data/`, `research/`, `docs/` found no `*nifty500*`, `*.gz`, or instrument-master file).
- **What is proven:** The publisher and URL pattern are correctly identified as NSE Indices' own file naming convention.
- **What is NOT proven:** Constituent count, field names, ISIN presence, symbol presence, as-of/revision date, and reproducibility — none of this was observed, because the file itself was never opened.
- **Status:** BLOCKED.

### B3-02
- **Source:** Upstox instrument-master documentation (`upstox.com/developer/api-documentation/instruments/`) and Search Instruments API documentation (`upstox.com/developer/api-documentation/instrument-search/`).
- **Access result:** Both documentation pages rendered as text via `WebFetch`. The actual instrument-master bulk file (`assets.upstox.com/.../NSE.json.gz`) and the live Search Instruments API (`api.upstox.com/v2/instruments/search`) were both unreachable (`403 from proxy after CONNECT` on both compute surfaces).
- **Evidence obtained:**
  - One verbatim equity example: `{"segment": "NSE_EQ", "name": "JOCIL LIMITED", "isin": "INE839G01010", "instrument_type": "EQ", "instrument_key": "NSE_EQ|INE839G01010", "trading_symbol": "JOCIL"}`.
  - The Search Instruments API's exact documented contract: `GET https://api.upstox.com/v2/instruments/search`, required `query` param (free text, ≤50 chars), optional `exchanges`, `segments`, `instrument_types`, `expiry`, `atm_offset`, `page_number`, `records` (max 30/page).
- **What is proven:** A deterministic construction pattern (`instrument_key = "NSE_EQ|" + isin`) is documented for equities, and a query-based lookup mechanism exists that — if reachable — would let each constituent be resolved individually without needing the bulk file.
- **What is NOT proven:** No actual constituent identity (B3-01, BLOCKED) and no actual instrument-master or live API response were obtained, so no real mapping — deterministic or otherwise — was tested against real data. Matched/unmatched/duplicate counts are not reported (none would be real).
- **Status:** NOT VERIFIED — a documented, credible mechanism exists (distinct from a bare "an endpoint exists" claim, since the exact endpoint, parameters, and one worked field-level example are now confirmed), but it has not been exercised, so it does not rise to VERIFIED.

### B3-03
- **Source:** Upstox Search Instruments API documentation; existing repo evidence (`config/symbols.py`).
- **Access result:** `api.upstox.com` (where a live search for "Nifty 500" would run) unreachable. `WebFetch` against the Search Instruments API doc page returned a verbatim INDEX example — but for NIFTY 50, not NIFTY 500: `{"name": "Nifty 50", "segment": "NSE_INDEX", "exchange": "NSE", "instrument_key": "NSE_INDEX|Nifty 50", "exchange_token": "26000", "trading_symbol": "NIFTY", "instrument_type": "INDEX"}`. The documentation page itself states no NIFTY 500 example is shown.
- **Evidence obtained:** This repo's own `config/symbols.py` line 36 independently confirms the *same* `NSE_INDEX|Nifty 50` value is real and already exercised for NIFTY 50 — corroborating (not proving) that the general index-key pattern `NSE_INDEX|<display name>` is correct for NSE indices, but this is a different index's confirmed value, not NIFTY 500's.
- **What is proven:** The general index-key naming pattern is genuinely confirmed twice (once in Upstox's own docs, once in this repo's exercised code) for a *different* index.
- **What is NOT proven:** The literal instrument_key string for the NIFTY 500 index. Per this task's explicit instruction, `"NSE_INDEX|Nifty 500"` is NOT recorded as verified — it is a plausible but unconfirmed guess by pattern, and is not used anywhere in this report as if it were established.
- **Status:** BLOCKED.

### B3-04
- **Source:** NSE Indices classification / NIFTY 500 CSV `Industry` column (if any) / NSE's industry-classification page.
- **Access result:** `niftyindices.com` CSV unreachable (same as B3-01). `nseindia.com` and every tested subdomain (`www.`, `static.`, `archives.`, `nsearchives.`) rejected identically — the industry-classification page could not be independently re-fetched this task.
- **Evidence obtained:** None. `equity_intel/persistence/schema.py` does define a `sector TEXT` column (and `isin`, `instrument_key` columns) in its schema, but this is an unpopulated placeholder column in a non-functional scaffold — it is evidence of an intended design, not evidence of an actual sector value or source.
- **What is proven:** Nothing about the actual sector/industry field content, coverage, or publisher-side taxonomy definition.
- **What is NOT proven:** Whether NSE Indices' free/bundled data even contains a usable field, whether it's labeled "Sector" or "Industry", and whether it satisfies the approved "authoritative NSE/Nifty Indices classification" requirement versus needing the (previously reported) subscription-only full taxonomy.
- **Status:** BLOCKED.

### B3-05
- **Source:** Upstox V3 Historical Candle API; `core/historical_data.py`.
- **Access result:** `api.upstox.com` unreachable on both compute surfaces (same control-domain-verified rejection as B3-01/02/03).
- **Evidence obtained (from existing repo code, inspected directly this task):** The endpoint `GET https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}` is documented and coded, with `unit="days"` a valid, supported value, and response rows parsed into `["timestamp","open","high","low","close","volume","oi"]`. The endpoint is generic per `instrument_key` — nothing restricts it to indices. However, this repo's actual, exercised usage is 100% index-only (`NIFTY_INSTRUMENT_KEY`, 1/5/15-minute intraday), never daily, never any equity. The module's own header comment states explicitly it "cannot be exercised end-to-end in a sandbox with no Upstox account and no egress to api.upstox.com," and its test suite uses a fake `fetch_fn` that never contacts the real API.
- **What is proven:** The documented contract supports daily bars generically by instrument_key.
- **What is NOT proven:** That a real equity instrument actually returns valid daily OHLC over a 252-session window — no such call has ever been made, live or cached, by this repository or this task. "Documented + coded" is explicitly distinguished from "successfully exercised" per this task's own instruction.
- **Status:** BLOCKED — no minimal controlled equity example could be exercised because `api.upstox.com` was unreachable.

### B3-06
- **Source:** Upstox V3 Historical Candle API, `volume` field; `core/historical_data.py`.
- **Access result:** Same as B3-05 — `api.upstox.com` unreachable, no equity call possible.
- **Evidence obtained:** This repo's own code (`candles_to_bars` docstring) states, as an already-observed fact from real historical usage: the NIFTY *index's* candles carry `volume=0` in every row ever fetched. Per this task's explicit rule, this is NOT used as equity-volume evidence — it neither confirms nor denies what an equity instrument's volume field looks like.
- **What is proven:** The response schema includes a `volume` field, and this repo's parsing code passes it through unmodified (no fabrication).
- **What is NOT proven:** Whether Upstox equity daily candles carry real (non-zero) volume — no equity instrument's volume has ever been observed by this repository or this task.
- **Status:** BLOCKED.

### B3-07
- **Source:** NSE Exchange Communications holidays page (`www.nseindia.com/resources/exchange-communication-holidays`); archival/data subdomains tested as alternates.
- **Access result:** `WebFetch` against the holidays page rendered readable content (unlike the raw-file paths). Direct `curl` to the same host and to `archives.nseindia.com` / `nsearchives.nseindia.com` / `static.nseindia.com` (tested this task specifically as possible structured-data alternates) all failed identically (`403 from proxy after CONNECT`).
- **Evidence obtained:** One verbatim confirmed date: "November 08, 2026, shall be a trading holiday on account of Diwali Laxmi Pujan." The page's own text states the full year/product holiday list "loads dynamically via JavaScript or an API call" and is not present in static content.
- **What is proven:** Official source identity (NSE's own Exchange Communications page) and one real holiday date.
- **What is NOT proven:** The full 2026 Capital Market holiday list, weekend treatment beyond the obvious calendar fact, special-session representation, or any deterministic, reproducible mechanism to construct 252 completed trading sessions.
- **Status:** BLOCKED.

## 5. Access Failures

| Host / Endpoint | Method | Failure |
|---|---|---|
| `niftyindices.com/IndexConstituent/ind_nifty500list.csv` | `curl` (device + cloud sandbox) | `403 from proxy after CONNECT` / `CONNECT tunnel failed, response 403` |
| `niftyindices.com/IndexConstituent/ind_nifty500list.csv` | `WebFetch` | Content reported as unreadable binary |
| `www.nseindia.com` | `curl` (device + cloud sandbox) | `403 from proxy after CONNECT` |
| `archives.nseindia.com` | `curl` (device) | `403 from proxy after CONNECT` |
| `nsearchives.nseindia.com` | `curl` (device) | `403 from proxy after CONNECT` |
| `static.nseindia.com` | `curl` (device) | `403 from proxy after CONNECT` |
| `assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz` | `curl` (device + cloud sandbox) | `403 from proxy after CONNECT` |
| `api.upstox.com` (base host, no live call attempted since unreachable) | `curl` (device + cloud sandbox) | `403 from proxy after CONNECT` |
| `upstox.com/developer/api-documentation/get-market-quote` | `WebFetch` | `404` — page does not exist at this path (documentation page, not a network-policy block) |

Control-domain test (same shells, same task run): `github.com` returned
`200` from the device shell, confirming the above are organization
egress-policy rejections, not general network failure. No credentials or
secrets are exposed anywhere in this report; `config/.token_cache.json`
was inspected only for key names and `issued_at` metadata (an
`access_token` field exists, value not read or logged) — it is moot for
this task since `api.upstox.com` is unreachable regardless of token
validity, so it was not used to attempt any call.

## 6. Existing-Repository Evidence

- `config/symbols.py`: one real, previously-exercised index key
  (`NSE_INDEX|Nifty 50`) exists; no equity ISIN, no equity
  `upstox_instrument_key`, and no NIFTY 500 entries exist anywhere.
- `core/historical_data.py`: documents and codes the V3 daily/intraday
  candle endpoint generically, but has only ever been exercised (and
  only via a fake test harness, never live) against the NIFTY 50 index,
  intraday. Its own comments state it cannot be exercised end-to-end
  without real Upstox network access, which this environment does not
  have.
- `equity_intel/persistence/schema.py`: defines placeholder `sector`,
  `isin`, and `instrument_key` columns — an intended design, not
  populated or sourced data.
- `requirements.txt`: no Upstox SDK or NSE-data package dependency found.
- No file anywhere in the repository (`core/`, `equity_intel/`,
  `config/`, `data/`, `research/`, `docs/`) contains a NIFTY 500
  constituent list, an Upstox instrument-master file, a sector mapping,
  or a trading-holiday calendar.

## 7. Overall Gate

B3 SOURCE VERIFICATION:
**BLOCKED**

DATA ACQUISITION GATE:
**BLOCKED**

(B3-01 BLOCKED, B3-02 NOT VERIFIED, B3-03 BLOCKED, B3-04 BLOCKED, B3-05
BLOCKED, B3-06 BLOCKED, B3-07 BLOCKED — none reach VERIFIED, so per this
task's own rule the gate cannot be opened even partially.)

## 8. Remaining Blockers

1. Organization egress policy rejects `niftyindices.com`,
   `nseindia.com` and every tested subdomain, `assets.upstox.com`, and
   `api.upstox.com` on both available compute surfaces — confirmed
   against a working control domain in this task's own run. This is the
   root blocker for B3-01, B3-02 (mapping test), B3-03, B3-04, B3-05,
   and B3-06.
2. `WebFetch` can reach some `upstox.com/developer/...` documentation
   pages but not raw data files, and the NSE holidays page's actual
   date list is client-side/dynamic and not present in fetched static
   content — this is the specific blocker for B3-07's full calendar.
3. B3-04's Industry-vs-Sector equivalence question remains unresolved
   independent of retrieval, since the source field has never been
   opened by any task to date.
4. No equity-instrument evidence (OHLC or volume) has ever been
   obtained by this repository, live or cached — B3-05/B3-06 rest
   entirely on a generic, documented endpoint contract and an
   index-only usage history, not an actual exercise.
5. A cached Upstox access token exists in
   `config/.token_cache.json` (issued 2026-09-22), but it is moot: even
   if valid, `api.upstox.com` is unreachable from this environment
   regardless of token validity, so it could not be exercised and was
   not attempted.

## 9. Non-Actions

- No bulk data acquired: confirmed — every retrieval attempt failed
  before any file bytes were obtained.
- No permanent market data stored: confirmed.
- No code implementation performed: confirmed — no file outside this
  report was modified.
- No dashboard changes: confirmed.
- No engine changes: confirmed (`core/continuous_engine.py`,
  `core/paper_engine.py` untouched).
- No OMS changes: confirmed (`core/oms/*` untouched).
- No risk-manager changes: confirmed.
- No B2 changes: confirmed.
- No live trading: confirmed — no broker call of any kind was made.
- No pytest run: confirmed — not required, since no code-level
  verification was performed (all inspection was read-only file/doc
  reading).

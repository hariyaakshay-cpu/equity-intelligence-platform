# B3 HUMAN DECISION ADJUDICATION — 2026-09-22

Governance-only. Read-only investigation except for this single document.
No data acquisition, no code changes, no implementation. This report
records the human decisions supplied for B3 and verifies, from
repository-available evidence only, whether the intended architecture can
actually obtain the required inputs. Human decisions resolve governance
intent; they do not by themselves resolve technical/source availability.

## 1. Human Decisions

- **D-B3-01 (Universe):** NIFTY 500 stocks. The Equity Intelligence
  universe is the NIFTY 500 constituents; not NIFTY 50/100/Midcap/
  Smallcap or an independently constructed list. The authoritative
  constituent source itself still requires verification (this document,
  Section 2.1).
- **D-B3-02 (Equity data vendor):** UPSTOX is the designated primary
  authorized source for B3 equity market data. yfinance must not be
  silently substituted. If Upstox cannot supply a required dataset, the
  deficiency is to be reported, not silently worked around.
- **D-B3-03 (Relative-strength benchmark):** NIFTY 500 INDEX itself is
  the benchmark for the B2 Relative Strength component. NIFTY 50 must
  not be substituted merely because NIFTY 50 data already exists in the
  repository. The exact Upstox instrument representation of the NIFTY
  500 benchmark still requires verification (Section 2.3).
- **D-B3-04 (Sector mapping):** Every NIFTY 500 constituent must carry
  an explicit sector mapping, sourced from an authoritative NSE/Nifty
  Indices classification — not manually invented, not inferred from
  company name, not an unapproved third-party taxonomy. Source,
  taxonomy version, effective date, and mapping mechanism all still
  require verification (Section 2.4).
- **D-B3-05 (History/session basis):** 252 TRADING SESSIONS, not
  calendar days, is the basis for the 52-week/structure completeness
  check. No calendar-day approximation permitted. The trading-calendar
  source itself still requires verification (Section 2.5).
- **D-B3-06 (Data acquisition):** Approved IN PRINCIPLE — acquisition of
  constituent metadata, equity daily OHLC, equity daily volume, NIFTY
  500 benchmark history, sector metadata, and trading-session/calendar
  metadata may proceed once the source-verification gate passes. This
  approval does NOT authorize acquisition during this task; acquisition
  is a separate, later task.

## 2. Source Verification

### 2.1 NIFTY 500 Universe

No NIFTY 500 constituent list, file, or reference to one exists anywhere
in this repository (confirmed by search of `config/`, `core/`,
`brokers/`, `dashboard/`, `docs/`, `equity_intel/`, `scripts/`,
`strategies/`, `tools/` for "nifty.?500" / "nifty500" — the only hits are
this task's own governance documents and the `equity_intel/` scaffold's
own field names, neither of which is a data source).

Outside repository evidence: NSE Indices Limited (the index-governance
subsidiary of NSE) publishes an official NIFTY 500 constituent list
(commonly distributed as a downloadable CSV, e.g.
`ind_nifty500list.csv`, from niftyindices.com), reconstituted on a
periodic (semi-annual) schedule with a stated effective date. This is
general market-structure knowledge, not something confirmed from within
this repository or this sandboxed session — this task did not fetch,
browse, or reach any external network location to confirm current
reachability, current file format, or current effective date. No
download was attempted (none is permitted by this task).

**Verification questions:**
1. Does the official source provide the constituent list? — Plausible
   per general knowledge of NSE Indices' publishing practice, but NOT
   independently confirmed from this session/environment.
2. Identifiable and reproducible? — A named, versioned/dated
   publication is the general pattern; not independently confirmed here.
3. Deterministic obtainable form? — Not confirmed here.
4. Effective/as-of date or versioning? — Not confirmed here.
5. Suitable for historical reproducibility? — Cannot be assessed without
   inspecting the actual source and its versioning history.
6. Symbols mappable to Upstox? — See Section 2.2; the mapping mechanism
   (Upstox's own instrument master) is technically plausible but has
   never been exercised in this repository against equity symbols.

**Result: SOURCE NOT VERIFIED FROM REPOSITORY EVIDENCE.** No download
was performed (correctly, per task scope). B3-01 remains open pending an
actual reachability/format check of the named external source — a check
this task was not authorized to perform.

### 2.2 Upstox Equity Data

Repository evidence (verified, not assumed):

- `core/historical_data.py` (module docstring, lines 5-45) documents,
  as "confirmed via Upstox's own developer docs, not assumed" at the
  time it was written, the V3 Historical Candle Data endpoint:
  `GET https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}`,
  with `unit` in `{minutes, hours, days, weeks, months}` and `interval`
  1 for `days`. This endpoint is generic over `instrument_key` — it is
  not NIFTY-specific in its contract, only in how this repo currently
  calls it (only ever with the NIFTY 50 index key).
- `core/historical_data.py`'s `_rows_to_dataframe()` (lines 133-151)
  confirms the candle row shape actually consumed includes
  `open, high, low, close, volume, oi` alongside `timestamp` — i.e. the
  endpoint returns volume, not just OHLC.
- `brokers/upstox_adapter.py` (`UpstoxSymbolResolver`, lines 1231-1263)
  documents and partially implements consumption of Upstox's published
  complete NSE instrument master:
  `https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz`,
  described in-repo as "published daily". The existing resolver code
  only parses this file's option-contract fields
  (`name|strike|option_type|expiry` → `instrument_key`); it has never
  been exercised in this repository against the file's cash-equity or
  index records.
- No code, comment, or document in this repository confirms an
  `instrument_key` for any individual equity stock (RELIANCE, TCS,
  HDFCBANK, INFY, ICICIBANK, WIPRO, BAJFINANCE, TATASTEEL — the 8 stock
  entries in `config/symbols.py` — none carry an `upstox_instrument_key`
  field; only the NIFTY 50 index entry does).
- No rate-limit or max-date-range figures for the historical-candle
  endpoint are confirmed in-repo; `core/historical_data.py`'s own
  comments flag these as never independently confirmed and defaulted
  conservatively.

**Result: PARTIAL / MECHANISM IDENTIFIED, NOT CONFIRMED FOR EQUITIES.**
Upstox's historical-candle endpoint is verified (via this repo's own,
previously-confirmed integration) to be capable of returning daily
OHLC+volume for an arbitrary `instrument_key`. Upstox's instrument
master file is verified to exist and to be Upstox's documented mechanism
for obtaining `instrument_key` values in bulk. Neither has ever been
exercised in this repository against an equity cash-market instrument or
against a NIFTY 500-scale symbol set. This is a real, named, technically
plausible path — not a confirmed one for the equity use case. If it
turns out not to cover a required dataset (e.g. an equity segment field
this repo has never parsed), that gap must be reported when acquisition
is actually attempted, per D-B3-02's own instruction, not assumed away
here.

### 2.3 NIFTY 500 Benchmark

No Upstox instrument_key for a "NIFTY 500" index exists anywhere in this
repository. `config/symbols.py` confirms only one index instrument_key
end-to-end: `"NSE_INDEX|Nifty 50"` for the NIFTY 50 index, explicitly
sourced from `core/upstox_data.py`'s `get_option_chain()` default
parameter. No equivalent has ever been established for NIFTY 500.

Upstox's instrument master file (Section 2.2) is the documented general
mechanism through which an index instrument_key would be obtained (index
entries such as `NSE_INDEX|Nifty 50` are drawn from exactly this kind of
master listing), which makes it plausible that a `NSE_INDEX|Nifty 500`
or equivalent key exists in that master file — but this has not been
downloaded or inspected in this task (data acquisition is out of scope
here), so this is not a confirmed mapping.

Per this task's explicit instruction not to guess the instrument key:

**BENCHMARK INSTRUMENT MAPPING UNRESOLVED.**

Only the NIFTY 50 index has historical daily data currently present in
this repository (`data/historical/NIFTY_*.csv`), and per D-B3-03 that
data must not be substituted for the NIFTY 500 benchmark. No NIFTY 500
benchmark history exists anywhere in this repository.

### 2.4 Sector Classification

No sector taxonomy, sector-classification file, or per-symbol sector
mapping exists anywhere in this repository outside the `equity_intel/`
scaffold's own field names (`market_data.py`, `persistence/schema.py`,
`tests/test_contracts.py`, `__init__.py` — all of which declare a
`sector` field/column as structure only, with no data and no source
attached, consistent with the scaffold's non-functional design).

No document in this repository names an authoritative NSE/Nifty Indices
sectoral classification taxonomy, its version, its effective date, or
its constituent-mapping mechanism.

**Result: SOURCE NOT ESTABLISHED.** D-B3-04 requires an authoritative
NSE/Nifty Indices classification source; none is identified, named, or
verified anywhere in this repository. This is a full open item, not a
partial one — unlike Sections 2.2/2.3, there is no in-repo technical
mechanism to point to at all.

### 2.5 Trading Calendar / 252 Sessions

No trading-calendar file, NSE/BSE holiday list, or session-schedule
source exists anywhere in this repository (`*calendar*` / `*holiday*`
search across the working codebase returns only unrelated hits — the
"calendar spread" options strategy name — and no calendar-data file).

No document establishes: the authoritative trading-calendar source;
weekend/holiday handling; special/truncated session handling;
missing-session treatment; or whether "252" means 252 completed sessions
with the current, in-progress session excluded. The prior B2 sensitivity
study's own D18 (a related B2 threshold) is itself listed there as
unresolved for the same underlying reason: no calendar source exists.

**Result: SOURCE NOT ESTABLISHED.** D-B3-05 fixes the *definition*
(252 trading sessions, not calendar days) but supplies no source for
determining which calendar days are actually sessions. This remains a
full open item.

## 3. Previous B3 Blocker Closure

| Blocker | Human Decision | Source Verified? | Status | Remaining Action |
|---|---|---|---|---|
| B3-01 (NIFTY 500 universe) | D-B3-01: NIFTY 500 stocks | NO — external source not reachable/inspected from this session | REMAINS BLOCKED | Verify NSE/Nifty Indices source reachability, format, and versioning; establish deterministic acquisition method |
| B3-02 (symbol/instrument mapping) | D-B3-02: Upstox | PARTIAL — mechanism (instrument master file) identified and repo-verified for options; never exercised for equities | SOURCE VERIFICATION FAILED (incomplete) | Download and inspect Upstox instrument master's equity-segment records against a real NIFTY 500 symbol list once B3-01 resolves |
| B3-03 (benchmark) | D-B3-03: NIFTY 500 index | NO — no Upstox instrument_key established for NIFTY 500 | REMAINS BLOCKED | Establish NIFTY 500 instrument_key from Upstox's instrument master; acquire benchmark history |
| B3-04 (sector taxonomy/mapping) | D-B3-04: authoritative NSE/Nifty Indices source | NO — no source identified at all | REMAINS BLOCKED | Identify and name the authoritative taxonomy source, its version and effective date |
| B3-05 (equity OHLC history) | D-B3-06: approved in principle, vendor = Upstox | PARTIAL — endpoint mechanism verified generically, never exercised for any equity symbol | REMAINS BLOCKED (dependency chain) | Depends on B3-01/B3-02; acquisition itself is a separate future task |
| B3-06 (equity volume history) | D-B3-06: approved in principle, vendor = Upstox | PARTIAL — same endpoint returns `volume`, never exercised for equities | REMAINS BLOCKED (dependency chain) | Same as B3-05; tracked separately per prior audit's instruction |
| B3-07 (trading calendar) | D-B3-05: 252 trading sessions | NO — no calendar source exists anywhere in repo | REMAINS BLOCKED | Identify and name an authoritative NSE/BSE trading-calendar source |
| B3-08 (authorized equity data vendor) | D-B3-02: UPSTOX | RESOLVED IN PRINCIPLE (governance decision made); technical completeness for equities not yet demonstrated | RESOLVED IN PRINCIPLE | No further governance action required; technical demonstration deferred to actual acquisition task |

## 4. B2 Dependencies

Per governance rule, B2 itself is not modified or re-adjudicated here.
This section only checks whether the human decisions supply the *inputs*
B2's components will eventually need.

- **Trend / Momentum / Volume / Structure(52W) / ATR-context:** all
  require equity daily OHLC(+volume) history. D-B3-06 approves
  eventual acquisition via Upstox in principle; no such history exists
  yet, and the acquisition mechanism is unexercised for equities
  (Section 2.2). Still B3-BLOCKED, now with a named vendor and a named
  (if unconfirmed) mechanism instead of no vendor at all.
- **Relative Strength (benchmark-dependent):** D-B3-03 names the
  benchmark (NIFTY 500 index) but its Upstox instrument representation
  is unresolved (Section 2.3) and no benchmark history exists. Still
  BOTH B2- and B3-blocked: B2's own D03/D04 threshold decisions are
  separate from this data-availability question and are untouched here.
- **expected_asof_date / 252-session completeness:** D-B3-05 fixes the
  definition (252 trading sessions) but the calendar source needed to
  compute it deterministically does not exist (Section 2.5). Still
  blocked.
- **Composite aggregation, candidate cutoff, watchlist limit/K,
  classification tags, reason codes, ranking:** unaffected by this
  task's decisions — these remain B2-only blockers (unresolved
  thresholds D01-D19), not addressed here and not claimed to be.

No new B2 dependency is created or resolved by this task; this section
is a status check only.

## 5. Data Acquisition Gate

Per Phase 9's seven conditions:

1. NIFTY 500 constituent source verified — **NO** (Section 2.1)
2. Upstox equity historical-data capability verified — **NO** (partial:
   generic mechanism confirmed, equity-specific exercise absent —
   Section 2.2)
3. NIFTY 500 benchmark representation verified — **NO** (Section 2.3)
4. Sector mapping source verified — **NO** (Section 2.4)
5. 252-session calendar basis verified — **NO** (Section 2.5)
6. Symbol/instrument mapping mechanism verified — **NO** (mechanism
   identified, not exercised for equities — Section 2.2)
7. No unresolved governance contradiction remains — **YES** (the six
   human decisions are internally consistent with each other and with
   B1's freeze exception and B2's own unresolved-threshold state; no
   contradiction was found)

Condition 7 alone does not pass the gate; conditions 1-6 all fail.

**DATA ACQUISITION GATE = BLOCKED.**

## 6. Remaining Blockers

1. B3-01 — No verified, reachable, reproducible NIFTY 500 constituent
   source (human decision made; source itself unverified).
2. B3-02 — Upstox equity-segment instrument mapping never exercised;
   no equity `instrument_key` established for any symbol.
3. B3-03 — No Upstox instrument_key established for the NIFTY 500
   benchmark; no benchmark history exists.
4. B3-04 — No authoritative sector/taxonomy source identified at all.
5. B3-05/B3-06 — No equity OHLC or volume history exists; acquisition
   mechanism unexercised; blocked on B3-01/B3-02.
6. B3-07 — No trading-calendar source identified at all.

B3-08 (vendor authority) is the one blocker now closed at the governance
level (RESOLVED IN PRINCIPLE) by D-B3-02; its technical completeness for
the equity use case is still undemonstrated but is no longer a
governance open item.

## 7. Explicit Non-Actions

Data acquired: NO. NIFTY 500 downloaded: NO. Historical equity data
downloaded: NO. Benchmark data downloaded: NO. Sector mapping
downloaded: NO. Scanner implemented: NO. Scoring implemented: NO.
Candidate selection implemented: NO. Watchlist implemented: NO.
Dashboard modified: NO. Trading engine modified: NO. OMS modified: NO.
Risk manager modified: NO. B2 modified: NO. `config/symbols.py`
modified: NO (read-only inspection only). Credentials created: NO.
Broker integration modified: NO. Pytest: NOT RUN. Application: NOT RUN.
Live trading: NO. `__pycache__` cleanup: NOT ATTEMPTED.

## 8. Final Adjudication

**B3 SOURCE VERIFICATION INCOMPLETE**
**DATA ACQUISITION GATE = BLOCKED**

The human decisions (D-B3-01 through D-B3-06) resolve governance intent
completely and without internal contradiction. They do not, by
themselves, establish that the intended architecture can actually obtain
the required inputs. Of the eight previously registered blockers, one
(B3-08, vendor authority) is now closed at the governance level. The
remaining seven are still open: four (B3-01, B3-03, B3-04, B3-07) have
no source identified or verified at all from this repository, and three
(B3-02, B3-05, B3-06) have a technically plausible, repo-documented
mechanism (Upstox's historical-candle endpoint and instrument master
file) that has never been exercised against an equity instrument or a
NIFTY 500-scale symbol set. No data was acquired, downloaded, or
partially acquired during this task. Actual source-reachability
verification (confirming the NSE/Nifty Indices constituent and sector
sources are live, in what format, and under what versioning; and
confirming the Upstox instrument master's equity/index-segment content
against a real symbol) remains the next required step before the data
acquisition gate can open.

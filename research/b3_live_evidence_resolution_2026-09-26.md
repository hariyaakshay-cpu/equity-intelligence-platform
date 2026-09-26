# B3 Live Evidence Resolution — 2026-09-26

Status: EVIDENCE + DECIDED VERDICTS (B3-01 through B3-06); B3-07 remains OPEN

## 1. Provenance

- **Constituents CSV** (`data/reference/nifty500_constituents_2026-09-24.csv`): official NSE Indices file,
  `https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv`. Re-downloaded by Akshay on
  2026-09-26; SHA-256 identical to the committed file:
  `c043bdc21e6080f119a86eb28cdc9b3a6009d3baffa9b5d35e9ca41b195b4501`.
- **Instrument master** (`data/reference/upstox_NSE_instruments_2026-09-24.json.gz`, gitignored, untracked;
  SHA-256 `bf4a5db89c9e4129e5a281d9397e1f2d979ef8681e322e8479693fe20ba12331`): Upstox NSE instrument file
  dated 2026-09-24. Its keys were validated live this task against real Upstox API responses for MCX,
  HEGAM, and the Nifty 500 index (Section 2).

## 2. Evidence summary (raw numbers, no re-interpretation)

**Step 2 — constituent/instrument mapping:**
- Constituents CSV: 501 data rows; header `Company Name, Industry, Symbol, Series, ISIN Code`; 0 duplicate
  symbols; 0 duplicate ISINs; 0 blank fields.
- One row, `Dummy HEG Ltd. / DUMMYHEG / DUM545A01024`, does not match any `NSE_EQ` instrument by ISIN — its
  ISIN differs from the real `HEG Advanced Materials Ltd. / HEGAM / INE545A01024` (line 205) only by the
  `DUM` vs `INE` prefix, with an identical numeric suffix (`545A01024`).
- `HFCL Ltd. / HFCL / INE548A01028` has `Series = BE`, the only non-`EQ` series value in the file.
- Excluding the dummy row, all 500 remaining constituents map to **exactly one** `NSE_EQ` instrument by
  ISIN: 500 exactly-one matches, 0 no-match, 0 multiple-match.
- 13 `NSE_INDEX` records match "500" in name or trading_symbol, including exactly one plain
  `NSE_INDEX|Nifty 500` record alongside 12 named thematic/strategy sub-indices.

**Step 3 — live data pull (interval `1day`, 2025-08-22 to 2026-09-25):**
- Request URLs sent (no token):
  - `https://api.upstox.com/v3/historical-candle/NSE_EQ%7CINE745G01043/days/1/2026-09-25/2025-08-22`
  - `https://api.upstox.com/v3/historical-candle/NSE_INDEX%7CNifty%20500/days/1/2026-09-25/2025-08-22`
- Both MCX and the Nifty 500 index returned **271 sessions each**, over an **identical set of 271 trading
  dates** (0 dates present in one series but missing from the other).
- MCX rows around the 1:5 split ex-date (2026-01-02): close moved 2198.0 (2026-01-01) → 2216.0
  (2026-01-02) — no break of split magnitude.
- Source for the MCX corporate action: company-announced sub-division 1:5 (face value Rs 10 -> Rs 2),
  record date 2026-01-02 (T+1, so ex-date = record date), as reported in financial press coverage.
- MCX close[t]/close[t-1] ratios across all 271 sessions: **min 0.8834** (2026-01-30 → 2026-02-01),
  **max 1.0724** (2026-01-27 → 2026-01-28); 0 sessions with ratio < 0.8 or > 1.25.
- MCX `open_interest`: `0` on every one of the 271 rows (single distinct value: `[0]`).
- Nifty 500 index `volume`: `0` on every one of the 271 rows.
- HEGAM (`NSE_EQ|INE545A01024`, 2026-08-20 to 2026-09-25, 26 sessions): close ratio 2026-09-04 → 2026-09-07
  = **0.3738** (728.25 → 272.20).
- Source for the HEG corporate action: NSE Indices press release dated 2026-09-03 (demerger of the
  Graphite business into HEG Graphite Ltd; demerged entity included as DUMMYHEG at zero price, effective
  2026-09-07, close of 2026-09-04).
- 2026-02-01 is a **Sunday** with a real, distinct MCX session (open=2300.0, high=2319.9, low=2068.5,
  close=2233.3, volume=20,999,802 — a genuine, independently-valued row, not a duplicate of the adjacent
  Friday or Monday sessions).
- HEGAM's fetch window (2026-08-20 to 2026-09-25) contains 27 weekdays; exactly **one** weekday,
  **2026-09-14**, is absent from the 26 returned sessions.
- Scope: B3-05 and B3-06 evidence rests on two equities (MCX, HEGAM) and one index (Nifty 500).

## 3. Verdicts, decided by Akshay on 2026-09-26

| Item | Verdict |
|---|---|
| B3-01 | MET |
| B3-02 | MET |
| B3-03 | MET, using `NSE_INDEX\|Nifty 500` |
| B3-04 | MET for v1, using the CSV's 20-value `Industry` field, explicitly accepted as a v1 governance decision — not asserted to be NSE's formal Sector taxonomy |
| B3-05 | MET |
| B3-06 | MET |
| B3-07 | OPEN |

## 4. Design rules that follow (to be implemented later, not now)

a) Upstox daily history is split-adjusted retroactively, so stored candles must be **re-fetched over the
   full window, not appended**.
b) Demergers are **not** adjusted, so v1 detects and flags them (degraded data status, excluded from
   indicators); proper adjustment is deferred to a later version.
c) Exclude `DUMMY*` placeholder rows from the universe; flag non-`EQ` series (`BE` = trade-for-trade, no
   intraday).
d) The trading calendar must be a **positive list of actual sessions** (special sessions such as Sunday
   2026-02-01 exist), sourced for B3-07.

## 5. Still open

- **B3-07**: official NSE trading-holiday and special-session source, needed to build a positive session
  list per Section 4(d).
- **B2** (threshold source): unchanged — still BLOCKED, not addressed by this task.

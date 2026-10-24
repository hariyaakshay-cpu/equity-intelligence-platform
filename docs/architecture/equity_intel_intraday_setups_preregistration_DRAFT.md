# Equity Intelligence - Intraday Setup Pre-Registration (DRAFT v0)

Status: **DRAFT, NOT APPROVED. No implementation or data pull is authorized by this document.**
Drafted 2026-10-24 as the Phase 2 document of
`equity_intel_intraday_signals_spec_DRAFT.md` (Section 5). Written BEFORE any
intraday data has been examined: no number below comes from data.

Inherited, already decided (spec Section 3): strictly intraday, long only
(D1, D2); liquid subset of NIFTY 500, cut-off still open (D3); 5-minute bars,
max 5 signals per day (D4); direction and setup only, no stop/target/size (D5);
Stage 4 acceptance thresholds as recorded under D6.

A signal from any setup below must NOT be sent until that setup has passed
Stage 4 (spec Section 1). Until then these definitions are inputs to research only.

## 1. Common rules (apply to every setup)

- Session 09:15-15:30 IST from the verified NSE calendar; 75 five-minute bars.
- A rule may use only CLOSED bars up to and including bar t (no forming-bar values).
- Triggers at most once per symbol per setup per session.
- Does NOT trigger when: any bar needed by the rule is missing or stale; the bar
  has zero volume; the symbol has a corporate-action flag for the session
  (price basis rule); the symbol is outside the liquid subset (D3); the data
  snapshot is not COMPLETE; the Upstox token has expired.
- No signal after the last-signal time (proposal P5 below).
- Output contract is spec Section 7 (symbol, side=LONG, setup id+version, trigger bar
  time, snapshot id, freshness, disclaimer). No entry price, stop, target or size.

## 2. Setups (all LONG, all version v0)

### ORB_LONG v0 - opening-range breakout
- Opening range = highest high of the first N_or bars of the session (P1).
- Trigger: a bar closes above the opening-range high, with trigger time within
  the window [first bar after the range, T_orb_end] (P2).
- Does not trigger when: the opening range has fewer than N_or closed bars, or its
  width is zero.

### VWAP_RECLAIM_LONG v0 - reclaim of session VWAP
- Session VWAP = cumulative sum(typical price x volume) / cumulative volume over
  closed bars since 09:15, typical price = (high+low+close)/3.
- Trigger: previous closed bar closed at or below VWAP and this bar closes above
  VWAP, and the close is above the previous session's close (P3 context filter).
- Does not trigger: before bar index B_vwap_min (P4); if cumulative volume is zero.

### PDH_BREAK_LONG v0 - break of previous session high
- Trigger: first bar of the session whose close is above the previous session's high
  (previous session from the verified calendar, not "yesterday").
- Does not trigger: before 09:30; after the last-signal time (P5); if the previous
  session has no complete daily bar.

## 3. Parameters P1-P6 (CONFIRMED by Akshay 2026-10-24 as proposed; still no data basis, frozen at approval)

| Id | Meaning | Proposed |
|----|---------|----------|
| P1 | N_or, bars in opening range | 3 (09:15-09:30) |
| P2 | T_orb_end, last ORB trigger time | 11:30 IST |
| P3 | context filter for VWAP reclaim | close above previous session close |
| P4 | B_vwap_min, earliest VWAP trigger | bar 12 (10:15 IST) |
| P5 | last-signal time, all setups | 14:45 IST |
| P6 | tie-break when more than 5 triggers compete in the daily cap | first trigger time, then symbol A-Z (no score used, so it cannot import the provisional daily score) |

Parameters are frozen at approval. Any change is an amendment made before the next
experiment, never after seeing results (ML spec 9). Each setup+version+parameter
set is hashed and the hash is stored with every signal.

## 4. Open items (2026-10-25: owner delegated; D3, D7, D8, shadow N and max drawdown were DECIDED by Claude before any data was examined - see spec Section 3. Only the data probe remains, and it needs the owner's PC and token)

Original list:

- D3 liquidity cut-off (e.g. a turnover rule) - Akshay to set.
- D7 cost model inputs: brokerage plan, taxes/charges, slippage assumption.
- D8 where/when it runs and the daily Upstox token routine (token expires ~03:30 IST).
- Shadow-mode length N (spec Section 9, Phase 4).
- Max drawdown threshold (D6, still to be set).
- Phase 1 intraday data probe: `scripts/equity_intraday_probe.py` written 2026-10-24 (read-only,
  writes only research/intraday/*.json); it must run on Akshay's machine with his token. Its
  report decides the endpoint, history depth and window limits; nothing is assumed before it.

## 5. Approval checklist

- [x] P1-P6 confirmed 2026-10-24 (values as listed in Section 3)
- [ ] Three setups accepted as the full v0 list (no additions after data is seen)
- [ ] Open items in Section 4 owned and answered

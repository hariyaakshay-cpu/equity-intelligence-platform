# Upstox daily history depth — sample probe (2026-10-03)

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Purpose: before designing Tier 2–4 data work (ML spec Section 8), find out how
far back Upstox daily candles actually go. Read-only: the probe calls the V3
historical-candle endpoint and prints JSON. It opens no database and writes
nothing.

- Script: `upstox_history_depth_probe.py` (run from the repository root).
- Raw output: `upstox_history_depth_probe_2026-10-03.json`.
- Window: up to 2026-10-01, fetched in ten-year requests back to a 1996-01-01
  floor, stopping at the first empty decade.

## Results

| Instrument | Key | Role | Earliest | Latest | Sessions | Largest gap |
|---|---|---|---|---|---|---|
| RELIANCE | `NSE_EQ\|INE002A01018` | large cap | 2000-01-03 | 2026-10-01 | 6,652 | 6 days (2014-10-01 → 10-07) |
| VOLTAS | `NSE_EQ\|INE226A01021` | mid cap | 2003-01-01 | 2026-10-01 | 5,857 | 33 days (2004-05-21 → 06-23) |
| SWIGGY | `NSE_EQ\|INE00H001014` | recent listing | 2024-11-13 | 2026-10-01 | 467 | 4 days |
| VEDL | `NSE_EQ\|INE205A01025` | E4 break 2026-04-30 | 2003-01-01 | 2026-10-01 | 5,857 | 33 days (2004-05-21 → 06-23) |
| TMPV | `NSE_EQ\|INE155A01022` | demerged 2025 | 2000-01-03 | 2026-10-01 | 6,606 | 33 days (2004-05-21 → 06-23) |
| Nifty 500 | `NSE_INDEX\|Nifty 500` | benchmark | 1996-01-01 (floor reached) | 2026-10-01 | 7,636 | 8 days (1996-12-24 → 1997-01-01) |

## API behaviour

- A single daily request spanning more than ten years is refused with HTTP 400
  (tested: 2010-01-01 to 2026-10-01). Decade windows succeed.
- The recorded run made 23 requests (22 decade windows plus the over-limit
  test), with no other errors and no retries logged.

## Findings

1. **Depth is available.** Long-listed equities go back to 2000–2003, and the
   index to at least 1996. That is more than the 8 years Tier 4 would need.
   For long-listed names the binding constraints are universe (survivorship)
   and data quality, not vendor depth.
2. **Special sessions exist and are uneven across symbols.** Weekend-dated bars
   are genuine exchange sessions (Muhurat, Budget-day Saturdays, the 2024 DR
   drills, 2024-01-20). From 2003 on, Nifty 500 and RELIANCE have the same 30
   weekend sessions. VOLTAS, VEDL and TMPV have only the 9 from 2019-10-27
   onward. A verified calendar (spec 5A.1) is needed to tell missing bars from
   closed days.
3. **Vendor hole in 2004.** VOLTAS, VEDL and TMPV have no bars from 2004-05-24
   to 2004-06-22; RELIANCE and the index do.
4. **VEDL January 2005.** Two consecutive close jumps (×3.22 on 2005-01-14,
   ×2.48 on 2005-01-17), consistent with an unadjusted corporate action or a
   vendor error. To be examined in the data-quality audit.
5. **Threshold blind spot.** With E4's 0.5 / 2.0 ratio thresholds, the 2025 Tata
   Motors demerger in TMPV is not detected anywhere in its history. The
   2026-04-30 VEDL event (×0.351) is.

## Limits of this probe

Six instruments are a sample. It does not measure full-universe depth or
whether delisted or removed names are still served. Both belong to the
survivorship audit (spec 5A.2) and to historical data expansion.

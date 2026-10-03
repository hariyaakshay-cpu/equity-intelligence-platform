# Demerger handling: current limitation and where detection belongs (2026-10-03)

Status: DESIGN NOTE. Documents behaviour that exists today and assigns ownership of the gap. No code change.

## Why demergers are a separate problem

Splits and bonuses are divisor events: Upstox applies them to history at fetch time
(`research/upstox_adjustment_basis_check_2026-10-03.md`), so a fetched series is continuous across the ex-date.
Demergers are not adjusted by Upstox (design Section 11 and `AcquisitionReport.adjustment_status`). The parent's
price drops by the value of the spun-off business, by an amount specific to each event and not recoverable from the
price series alone. Nothing in this repo adjusts for it, and nothing here should: v1 flags, never adjusts.

## What exists today

| Mechanism | Covers demergers? |
|---|---|
| `features/breaks.py`: flag close-to-close ratio < 0.5 or > 2.0, truncate history at the break | Only large ones (HEGAM, -62.6%). A demerger with ratio in [0.5, 2.0] is **not detected**. |
| `features/adjustment_basis.py` (ADJUSTMENT_BASIS_STALE) | Yes, for an entry in `corporate_action_review.csv` effective on/after the run's IST fetch date. Applies to any `event_type`. |
| Scanner path: `is_under_review` over the fetched window | Yes for a non-RESOLVED CSV entry inside the window. **E4 does not use this**: an entry whose date falls *inside* a stored E4 series raises no flag. |

Resulting gap: a small demerger inside an E4 series, absent from the CSV, silently distorts every indicator that
spans it (EMAs, ATR, RSI, ROC, `relative_return`, distance from high). A demerger that is in the CSV but dated
inside the window is also not flagged by E4.

## Decision: detection belongs in a later corporate-action layer, not in E4

- E4 is a stateless computation over stored prices. A ratio near 1 is indistinguishable from an ordinary move without
  an external event record, so no price-only threshold in E4 can close the gap. Lowering `break_low_ratio` would trade
  it for false positives on ordinary limit moves.
- The fix is an event source (NSE corporate-actions data, which the adjustment check already used for verification)
  feeding one corporate-action table with symbol, ex-date, type and divisor/ratio. Both the ADJUSTMENT_BASIS_STALE
  check (events after fetch) and an in-window check (events inside a stored series, truncate or flag per symbol, as
  `breaks.py` does today) read from it. The manual CSV is then its reviewed override, not the only source.
- That layer is a v2 scope item (design Section 11 decision 2: "a corporate-actions feed is deferred to v2"). It is
  not started by this note, and E1-E4 behaviour is unchanged.

## Interim operating rule

Until that layer exists, a known demerger must be entered in `data/reference/corporate_action_review.csv`. It then
stales runs fetched before its ex-date. Treat indicators on a symbol with an in-window demerger as unreliable
whether or not E4 flagged it.

## Possible later increment (not decided)

A cheap E4 addition within the current design: also mark a symbol when a non-RESOLVED CSV entry falls inside its
stored series window, reusing `is_under_review`. It closes the second bullet of the gap only, and only for events
somebody already knows about.

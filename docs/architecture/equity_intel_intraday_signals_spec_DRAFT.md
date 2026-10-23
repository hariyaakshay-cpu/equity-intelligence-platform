# Equity Intelligence — Intraday Signals Specification (DRAFT)

Status: **DRAFT, NOT APPROVED. No implementation is authorized by this document.**
Drafted 2026-10-22. Corresponds to Stage 5 ("detect live/intraday") of the
gating order set 2026-10-03.

Every number or rule marked **TO BE SET** is a decision for Akshay, to be made
before any experiment it governs. Nothing here invents a threshold.

## 0. Purpose and scope

Produce intraday buy/sell **notifications** for NIFTY 500 equities (stock
picks, not derivatives), delivered to **Telegram and the dashboard only**.
Akshay places any trade himself. The equity side never places, modifies or
records orders.

Out of scope, each needing its own approved spec: B2 scoring, Trade Plan
(entry / stop / targets / sizing), order or paper-trade creation, options.

## 1. Preconditions (hard gates)

This spec may be approved now, but no phase below Phase 0 may start until:

1. ML research spec Section 12 steps 2-5 are complete (verified calendar,
   survivorship audit, point-in-time break rule, history depth).
2. Gating Stage 1 (data trust) is closed, including the adjustment-basis
   check run on a real split/bonus event (not yet run as of 2026-10-03).
3. Gating Stages 2-4 each produced a reviewed report: objective market/stock
   condition classification; setups defined without hindsight; evidence that
   setups have positive expectancy net of costs.

A signal that has not passed Stage 4 must not be sent, however it is labelled.

## 2. Frozen rules (inherited and extended)

- No import of brokers.*, paper_engine, continuous_engine, core.oms.* or any
  order path. Static import-boundary test, same style as
  `test_import_boundaries.py`, covers all new code.
- Never write to `data/equity_intel.db`. Intraday data lives in its own store
  (Section 4). Read daily data only through
  `get_read_only_connection`.
- No claim of "done" or "verified" in any report without the actual test
  output or diff.
- Every message and dashboard element carries `RESEARCH ONLY - NOT A TRADING
  RECOMMENDATION` until Akshay amends this rule.
- Signals are suppressed, never guessed, when data is stale, incomplete or
  the Upstox token has expired.

## 3. Decisions required from Akshay before approval

| # | Question | Why it matters |
|---|----------|----------------|
| D1 | Holding style: strictly intraday (square off same session) or can a signal imply delivery? **DECIDED 2026-10-24: strictly intraday, same-session square-off** | Defines cost model, short-side feasibility, exit logic |
| D2 | Long only, or also sell/short signals? **DECIDED 2026-10-24: long only** | Shorting is intraday-only in India; changes costs and universe |
| D3 | Universe: full NIFTY 500 or a liquid subset? **DECIDED 2026-10-24: liquid subset; liquidity cut-off TO BE SET** | Thin names make signals untradeable |
| D4 | Bar interval(s) and signal frequency cap per day **DECIDED 2026-10-24: 5-minute bars, max 5 signals per day** | Drives data volume, noise, notification fatigue |
| D5 | Does a signal ship with an invalidation / stop level? | Needs the separate Trade Plan spec if yes |
| D6 | Acceptance thresholds for Stage 4 (AUC/expectancy, min trades, drawdown, concentration) | Must be fixed before any result exists |
| D7 | Cost model inputs (brokerage plan, taxes, charges, slippage assumption) | Expectancy must be net of costs; not invented here |
| D8 | Where the process runs and when (PC on during market hours? token refresh routine) | Token expires ~03:30 IST; needs interactive login |

## 4. Data requirements

- Source: Upstox intraday candles (and later possibly a live feed). Which
  endpoint and limits to be confirmed against Upstox docs and a probe, not
  assumed.
- Separate store `data/equity_intraday.db` with the same guard pattern:
  forbidden-path check, tmp_path in every DB test, append-only immutable
  fetch snapshots tied to one run (as in scanner V1).
- Price basis follows `equity_intel_price_basis_rule.md`; corporate-action
  days are flagged and excluded from research until handled.
- Session handling from the verified NSE calendar only (no weekday guess).
- Per-bar completeness and staleness checks; only **closed** bars may feed
  any rule (no forming-bar values).
- Survivorship and point-in-time rules from ML spec 5A apply unchanged.

## 5. Setup definition (no hindsight)

- Setups are defined and pre-registered in a separate document **before**
  any intraday data is examined for outcomes. Each has an id, a version, a
  plain-language rule, inputs, and an explicit "does not trigger when" list.
- Candidate families to consider for pre-registration (names only, no
  parameters chosen): opening-range breakout/breakdown, VWAP reclaim/loss,
  prior-day high/low break, relative strength vs Nifty 500 intraday,
  volume expansion.
- Parameters are fixed at pre-registration. Tuning after seeing results is
  an amendment made before the next experiment, never after (ML spec 9).
- Rules use only information available at bar close at time t.

## 6. Expectancy validation

- Walk-forward with embargo; no overlapping train/test sessions.
- Metrics net of costs and slippage (D7), per setup, per side, per sector,
  per time-of-day bucket; date-block bootstrap intervals.
- Evidence gate written as a template **before** the run, with thresholds
  from D6. Concentration limits (no single symbol, sector or session
  dominating the result) in the style of ML spec 7.4 criterion 4.
- Minimum-sample rule per setup (**TO BE SET**); setups below it are
  reported as inconclusive, not as passing.
- Leakage audit is a release gate for every dataset version.

## 7. Signal output contract

A signal record contains: signal id, symbol, side, setup id and version,
trigger bar time (IST), data snapshot id, data freshness, and the disclaimer.
Entry price, stop, targets and size are **not** included unless D5 is
approved together with a Trade Plan spec.

- Append-only `signal_log`. Each signal later gets an outcome record
  written by a separate evaluator, so forward performance is auditable.
- De-duplication (same symbol, side, setup within a cooldown) and a daily
  cap (D4).
- Global kill switch: a file or setting that stops all sending without a
  code change.

## 8. Delivery

- Telegram: reuse `telegram_bot/sender.py` (token never logged). New
  message builder; the existing digest stays unchanged.
- Dashboard: a "Signals" tab, shown only once this spec is approved and
  Stage 4 has passed. It reads `signal_log` read-only. No new write routes.
- Dashboard banner and gated-items tab are updated by editing text only
  after the corresponding phase is approved.

## 9. Phases (stop and review after each)

| Phase | Deliverable | Gate to next |
|-------|-------------|--------------|
| 0 | This spec reviewed, D1-D8 answered, approved | Akshay approval |
| 1 | Intraday data probe, then acquisition + data-trust audit | Audit report accepted |
| 2 | Pre-registered setup document | Approved before any outcome is viewed |
| 3 | Offline expectancy experiment and report | Evidence gate passed |
| 4 | Shadow mode: signals logged, not sent, for N sessions (**TO BE SET**) | Forward results consistent with Phase 3 |
| 5 | Telegram delivery, then dashboard Signals tab | Akshay approval |

## 10. Tests required before Phase 5

Import-boundary and DB-boundary tests; staleness and expired-token
suppression; kill switch; dedup and cap; calendar edge cases (holidays,
early close); signal log is append-only; a dry-run mode that prints and
never sends.

## 11. Approval checklist

- [ ] D1-D8 answered
- [ ] Preconditions in Section 1 understood and accepted
- [ ] Out-of-scope list in Section 0 accepted
- [ ] Phase table in Section 9 accepted

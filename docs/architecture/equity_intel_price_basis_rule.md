# Price-basis rule: one acquisition run = one adjustment basis

Status: rule, decided 2026-10-17 (option A). Scope: `equity_intel/`, `dashboard/`, `scripts/`.

## Why

- `research/upstox_adjustment_basis_check_2026-10-03.md`: Upstox daily candles are split/bonus-adjusted at fetch
  time (four events, checked against NSE data; a small sample). Demergers are not adjusted.
- So stored prices carry the adjustment basis of the moment they were fetched. The fetch time of a run is
  `acquisition_runs.run_started_at`. Inside one run there is one basis. Two runs fetched either side of an ex-date
  have two bases.
- The existing safeguards do not cover this: `equity_intel/features/breaks.py` flags a close-to-close ratio break
  inside one series only, and the STALE rule concerns the last bar date, not the adjustment basis.

## Rule

1. Read `acquired_observations` and `acquired_benchmark` one acquisition run at a time (filter on `run_id`).
2. Never join, merge, concatenate or difference prices from two runs to build a feature, return, label, score or
   dataset. This includes any later dataset assembled for setup or expectancy work.
3. Comparing the stored content hashes of two runs is allowed for audit only. That is what the Snapshot Audit does,
   and it makes no claim about why a bar differs. This rule does not change that page.
4. A longer history comes from fetching it in one acquisition run, not from stitching older runs together.

## Enforcement

- `equity_intel/tests/test_price_basis_boundary.py` parses the source and requires every SQL string that reads
  (`FROM` or `JOIN`) either table to filter on `run_id`. It is a tripwire, not a proof: it cannot see SQL built from
  separate pieces, a wrong `run_id`, or a Python-side merge of rows from two runs.

## Not covered (not started)

- Detecting that an ex-date fell between two stored runs. That is option B, a separate dashboard phase, and needs
  `data/reference/corporate_action_review.csv`, which is header-only today.
- No schema or data change is part of this rule.

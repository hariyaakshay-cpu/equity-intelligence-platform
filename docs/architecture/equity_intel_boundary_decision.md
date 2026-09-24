# Equity Intelligence: execution-boundary decision

Date: 2026-09-24
Status: DRAFT (structural scaffold only; no scoring/data-acquisition decision)

## 1. What moved, and from where

`equity_intel/` was imported into this repository (`Equity - intraday`) from
`algo_trader` on 2026-09-24, together with its B2/B3 research
(`research/b2_threshold_sensitivity_study_2026-09-22.md`,
`research/b3_01_to_b3_07_final_resolution_2026-09-23.md`,
`research/b3_human_decision_adjudication_2026-09-22.md`), as an unmodified
copy (see commit `d15e4c5`). The import was faithful, including a
dependency that does not resolve in this repository:
`equity_intel/scanner/execution_guard.py` imported
`core.oms.execution_mode`, which exists in `algo_trader`'s `core.oms`
package but has no equivalent here -- this repo's `core/` package
(`core.providers`, `core.database`, `core.models`) is a different,
unrelated package that happens to share the top-level name `core`.
Because `core.oms.execution_mode` does not exist here, importing
`equity_intel.scanner.shell` (and therefore
`equity_intel/tests/test_execution_isolation.py` and
`equity_intel/tests/test_scanner_shell.py`) raised `ModuleNotFoundError`.

## 2. The replacement

The mode-based guard is replaced by two independent checks, neither of
which introduces a trading-mode concept into this repository. Both are
driven by a single canonical tuple, `FORBIDDEN_PREFIXES`, defined once in
`equity_intel/scanner/execution_guard.py` -- that module is the single
source of truth; `equity_intel/tests/test_import_boundaries.py` imports
the tuple from there rather than keeping its own copy, and
`test_import_boundaries.py::test_forbidden_prefixes_equals_the_explicitly_written_out_expected_set`
pins its value against an explicitly written-out expected set, so shrinking
or otherwise weakening it requires deliberately editing that test.

`FORBIDDEN_PREFIXES` is:

    brokers
    core.paper_engine
    core.continuous_engine
    core.execution_engine
    core.oms
    core.risk_manager
    strategies
    main
    core.historical_data

1. **Static import-boundary test** (`equity_intel/tests/test_import_boundaries.py`):
   parses every `.py` file under `equity_intel/` with `ast` and fails the
   test suite if any of the above is imported anywhere in the package.
   `core.oms` is banned as a whole prefix, with no exception -- there is no
   longer an authorized `core.oms.execution_mode` import, because that
   module does not exist in this repository at all.
2. **Runtime `sys.modules` guard** (`equity_intel/scanner/execution_guard.py`,
   `assert_no_forbidden_modules_loaded()`), called once at the top of
   `ScanPipeline.run()`: it raises `RuntimeError` if any module matching
   `FORBIDDEN_PREFIXES` is already present in `sys.modules` when the scan
   starts.

There is deliberately **no mode flag, no `TRADING_MODE` (or similar)
environment variable, and no reimplementation of an execution-mode
concept**. This repository has no live-trading path of any kind, so there
is nothing for a mode flag to distinguish between; introducing one would
add a trading concept that does not otherwise exist here, purely to
replace a check that can be expressed more simply as "is a forbidden
module loaded."

## 3. Known, accepted limitation

The runtime guard (`assert_no_forbidden_modules_loaded()`) runs **once,
at scanner start** (`ScanPipeline.run()`), not continuously. It catches a
forbidden module that is already loaded into the process at that moment,
but it does not re-check after `run()` returns, and it does not prevent a
forbidden module from being imported later in the same process after the
scan has started. Continuous protection against `equity_intel/` code
itself ever importing one of these modules is the job of the static
import-boundary test (Section 2, item 1), which covers every `.py` file
in the package regardless of when it runs. The runtime guard's role is
narrower: it protects against `equity_intel` being invoked from within a
process that has *already* loaded trading infrastructure for some other
reason, which the static test cannot see.

## 4. Reserved names

All nine entries in `FORBIDDEN_PREFIXES` (Section 2) are reserved: this
repository must never create its own module importable as `core.oms`,
`core.paper_engine`, `core.continuous_engine`, `core.execution_engine`,
`core.risk_manager`, `core.historical_data`, `brokers`, `strategies`, or
`main` (as an importable module), even where the new module's purpose
sounds similar to what those names mean in `algo_trader`. If
`equity_intel/` later needs, for example, its own historical-data access
module, it must be named differently (e.g. `equity_intel/data/history.py`,
not `core/historical_data.py` or anything importable as
`core.historical_data`) so that `FORBIDDEN_PREFIXES` continues to mean
exactly what it says and never has to special-case "this one's actually
ours."

`main` deserves a specific clarification because this repository already
has a real, legitimate `main.py` at its root (EIP's own entry point, unrelated
to `algo_trader`'s `main.py`): the reservation is against **importing** it
as a module (`import main`) in any process that also runs the scanner --
that is what `FORBIDDEN_PREFIXES` and the static/runtime guards check for.
Running EIP's `main.py` as a script (`python main.py`, i.e. under
`__main__`) is unaffected and fine; it is not an import of the `main`
module and neither guard flags it.

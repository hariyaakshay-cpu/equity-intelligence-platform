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

## 5. The canonical database path and the single-connection-module rule

The frozen architecture names exactly one on-disk database for this
package: `<repo_root>/data/equity_intel.db`. This is enforced the same
two-layered way as the module-import boundary (Section 2), by an
allow-list rather than a deny-list, because a deny-list of specific
forbidden names (`oms_state.db`, `oms_shadow.db`, `production_trading.db`)
would miss any new database added later, anywhere:

1. **`equity_intel/persistence/db_path_guard.py`**: `assert_allowed_db_path()`
   resolves the given path (following symlinks, normalizing `..`, strict=False
   so a not-yet-existing path is still checked) and accepts it only if it
   equals `CANONICAL_DB_PATH` (`<repo_root>/data/equity_intel.db`) resolved
   the same way. Everything else is refused, including a same-named
   `equity_intel.db` in the wrong directory, and including in-process/URI
   SQLite shorthand (`":memory:"`, `"file:...?mode=rw"`) rejected up front
   as not being a real file path at all.
2. **`equity_intel/tests/test_db_connection_boundary.py`** (static, parses
   source with `ast` like `test_import_boundaries.py`), enforcing an
   import-level rule rather than a call-based one (a call-based check that
   flags any `.connect(...)` attribute call regardless of the object would
   false-flag an unrelated `.connect()` method on something else entirely):
   `sqlite3` may be imported -- in any form, plain or aliased, `import` or
   `from ... import` -- only by `equity_intel/persistence/connection.py`
   (the single reserved, not-yet-created future connection module) or by
   test modules. Inside test modules, sqlite3 import is unrestricted, but
   any call actually resolved back to sqlite3's `connect` (tracked through
   real import aliases, never by attribute-name-only matching) must pass
   exactly one argument, the literal string `":memory:"`.

There is no filename-only rule and no tmp_path special case inside
`db_path_guard.py` itself: a test that needs a temporary canonical path
monkeypatches `CANONICAL_DB_PATH` directly (see
`equity_intel/tests/test_db_path_guard.py`), rather than the guard
accepting a second, looser rule that would widen what production code
could also get away with.

`equity_intel/tests/test_db_path_guard.py`'s symlink-refusal test
(`test_refuses_a_symlink_pointing_at_a_forbidden_file`) is skipped on any
machine without symlink-creation privilege (Windows: `WinError 1314`,
requiring Developer Mode or an elevated process) -- it is therefore not
exercised on the current development machine, and a skip there is
expected, not a gap to chase.

## 6. `core.database` and `sqlalchemy` are banned for equity_intel

This repo's own `core.database` package (SQLAlchemy `Base`/`engine`/
`SessionLocal`, used by `core.models.Company` and the rest of this
repo's application) is a different, unrelated package that happens to
share the top-level name `core` with `algo_trader`'s `core` (Section 1).
Unlike `core.providers` and `core.models`, which `equity_intel` is free to
import (`ALLOWED_CORE_PREFIXES` in `test_import_boundaries.py`),
`core.database` is deliberately **not** on that allow-list, and neither is
the `sqlalchemy` package itself:
`equity_intel/tests/test_db_connection_boundary.py::test_no_equity_intel_module_imports_core_database_or_sqlalchemy`
fails the test suite if anything under `equity_intel/` ever imports either.
`equity_intel`'s own eventual persistence work goes through
`db_path_guard.py` plus raw `sqlite3`, on its own schema
(`equity_intel/persistence/schema.py`), not through this repo's ORM layer
or its `Company`/`Base` models -- keeping `equity_intel`'s one database
independent of the rest of this repo's data layer, not just of
`algo_trader`'s.

`core.database` is **not** added to `FORBIDDEN_PREFIXES` in
`execution_guard.py` (Section 2): that runtime guard is unchanged by this
section, and remains scoped to trading-infrastructure modules. The
`core.database`/`sqlalchemy` ban here is enforced only by the static test
in item 2 above, not by a runtime `sys.modules` check, because unlike the
trading-infrastructure guard (which protects against `equity_intel` being
invoked from within a process that has *already* loaded forbidden code for
some unrelated reason -- Section 3), there is no equivalent scenario here:
`core.database` is this repo's own ordinary application code, routinely
loaded by `main.py` and other application modules in the very process that
might also run the scanner, so a runtime "is it already loaded" check
would misfire constantly and protect nothing. The static, source-level
check is the correct and sufficient boundary for this rule.

Known, accepted limitation shared by every static check in this document
(Section 2's import-boundary test and this section's connection/import
checks alike): a dynamic import (`importlib.import_module(...)`,
`__import__(...)`) cannot be detected by `ast`-based source parsing, since
no literal `import` or `from ... import` statement appears in the source
for the parser to see.

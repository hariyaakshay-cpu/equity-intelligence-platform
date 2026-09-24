"""Equity Intelligence -- isolated NIFTY 500 scanner package.

Governance: this package exists under the B1 freeze-policy exception dated
2026-09-21 (see docs/development_freeze_policy.md). It is a non-functional
structural scaffold only, authorized by the completed B2/B3 Structural Build
Boundary Audit (research/b2_b3_structural_build_boundary_audit_2026-09-22.md).

B2 (scoring thresholds) is DRAFT COMPLETE but NOT RELEASED -- no numerical
band, cutoff, or watchlist size in this package is authoritative.
B3 (NIFTY 500 universe / market-data source) is BLOCKED -- no vendor,
benchmark, or sector taxonomy is selected anywhere in this package.

This package MUST NOT import any of the following (forbidden-import list
from the B1 exception row):
    brokers.*
    core.paper_engine
    core.continuous_engine
    core.execution_engine
    core.oms
    core.risk_manager
    strategies.*
    main
    core.historical_data

core.oms is forbidden as a whole prefix, with no exception. This repository
has no core.oms package at all: equity_intel was imported from algo_trader
(commit d15e4c5), where core.oms.execution_mode existed and was used as a
live-mode guard; that module does not exist here. The canonical list above
lives in equity_intel/scanner/execution_guard.py as FORBIDDEN_PREFIXES, and
is enforced two ways: a static import-boundary test
(equity_intel/tests/test_import_boundaries.py) that fails the test suite on
any forbidden import, and a runtime sys.modules guard
(equity_intel/scanner/execution_guard.py) that raises if a forbidden module
is already loaded when the scanner starts. See
docs/architecture/equity_intel_boundary_decision.md for the full decision
record.

PAPER TRADING ONLY. This package creates no order, no position, and no
execution request of any kind. Its only permitted output is a row in a
paper_watchlist persistence store (not yet created by this scaffold).
"""

__all__: list[str] = []

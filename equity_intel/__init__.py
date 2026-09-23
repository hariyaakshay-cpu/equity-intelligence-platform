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
    core.oms.order_router
    core.oms.execution_service
    core.oms.paper_oms_adapter
    core.oms.db
    core.risk_manager
    strategies.*
    main
    core.historical_data

The single explicitly authorized exception is core.oms.execution_mode,
used only to refuse to run when the process execution mode is LIVE.

PAPER TRADING ONLY. This package creates no order, no position, and no
execution request of any kind. Its only permitted output is a row in a
paper_watchlist persistence store (not yet created by this scaffold).
"""

__all__: list[str] = []

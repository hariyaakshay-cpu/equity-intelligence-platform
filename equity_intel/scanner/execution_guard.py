"""The one explicitly authorized trading-infrastructure dependency.

Per the B1 freeze-policy exception (2026-09-21 row): "It uses the existing
core.oms.execution_mode mechanism (no new trading-mode flag) and the scan
raises RuntimeError if the process mode is LIVE." This module is the sole
place in equity_intel/ that imports anything under core.oms, and it imports
only core.oms.execution_mode -- never core.oms.db, core.oms.order_router,
core.oms.execution_service, or core.oms.paper_oms_adapter, all of which
remain on the forbidden-import list.

`assert_not_live` is a pure function of an ExecutionMode value so it can be
unit-tested without redeclaring the test process's own execution mode
(core.oms.execution_mode.declare_mode is set-once per process).
"""
from __future__ import annotations

from core.oms.execution_mode import ExecutionMode, get_process_mode


def assert_not_live(mode: ExecutionMode) -> None:
    """Raise RuntimeError if `mode` is LIVE. No-op otherwise."""
    if mode == ExecutionMode.LIVE:
        raise RuntimeError(
            "Equity Intelligence scan refused: process execution mode is LIVE. "
            "This package is PAPER TRADING ONLY and may never run under a LIVE "
            "process (B1 freeze-policy exception, 2026-09-21 row)."
        )


def assert_process_not_live() -> None:
    """Convenience wrapper that reads the real process mode and applies
    the guard above. Called once at the top of the scanner shell."""
    assert_not_live(get_process_mode())

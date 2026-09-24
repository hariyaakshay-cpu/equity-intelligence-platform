"""Runtime guard against loading trading-infrastructure modules.

This package has no live-vs-paper execution-mode concept: this repo has no
OMS, broker, or order-execution system at all (see
equity_intel/tests/test_import_boundaries.py for the static import-boundary
check, which is the primary defense). There is no mode flag, no
TRADING_MODE environment variable, and no execution-mode replacement here.

Instead, this guard performs a runtime check at scanner start: it raises if
any module matching FORBIDDEN_PREFIXES is already present in sys.modules.
This is a defense-in-depth check on top of the static import-boundary test:
it protects against one of these modules being loaded into the same
process by something other than equity_intel itself, not against
equity_intel importing it directly (the static test already catches that).

FORBIDDEN_PREFIXES is the single canonical forbidden-module list for this
package: equity_intel/tests/test_import_boundaries.py imports it from here
rather than defining its own copy, so the static test and this runtime
guard can never drift apart. See
docs/architecture/equity_intel_boundary_decision.md for the decision record.
"""
from __future__ import annotations

import sys

FORBIDDEN_PREFIXES = (
    "brokers",
    "core.paper_engine",
    "core.continuous_engine",
    "core.execution_engine",
    "core.oms",
    "core.risk_manager",
    "strategies",
    "main",
    "core.historical_data",
)


def assert_no_forbidden_modules_loaded() -> None:
    """Raise RuntimeError if any forbidden trading-infrastructure module is
    already present in sys.modules. No-op otherwise."""
    loaded = sorted(
        name
        for name in sys.modules
        for forbidden in FORBIDDEN_PREFIXES
        if name == forbidden or name.startswith(forbidden + ".")
    )
    if loaded:
        raise RuntimeError(
            "Equity Intelligence scan refused: forbidden trading-infrastructure "
            f"module(s) already loaded in this process: {loaded}. This package "
            f"must never run in the same process as: {', '.join(FORBIDDEN_PREFIXES)}."
        )

"""Execution-isolation tests -- structural, not trading tests.

These prove that the runtime guard (equity_intel.scanner.execution_guard)
refuses to run if a forbidden trading-infrastructure module is already
loaded into the process, and is a no-op otherwise. No order (paper or
live) is placed by any test in this module, and no forbidden module is
ever really imported here -- a fake module object is injected into
sys.modules via monkeypatch and removed automatically at teardown.

Both the forbidden-module and near-miss cases are parametrized over
equity_intel.scanner.execution_guard.FORBIDDEN_PREFIXES (the single
canonical list also used by test_import_boundaries.py), so a future change
to that tuple is automatically exercised here without editing this file.
"""
import inspect
import sys
import types

import pytest

from equity_intel.scanner.execution_guard import (
    FORBIDDEN_PREFIXES,
    assert_no_forbidden_modules_loaded,
)
from equity_intel.scanner.shell import ScanPipeline

# One deliberately-similar-but-distinct name per entry in FORBIDDEN_PREFIXES,
# in the same order, proving the guard does not over-match on a substring.
NEAR_MISS_NAMES = (
    "brokerage",
    "core.paper_engines",
    "core.continuous_engine_v2",
    "core.execution_engines",
    "core.omsx",
    "core.risk_managers",
    "strategiesx",
    "mainx",
    "core.historical_database",
    # Python's own name for a running script's module, distinct from the
    # forbidden "main" module -- must never be flagged.
    "__main__",
)


@pytest.mark.parametrize("forbidden_module_name", FORBIDDEN_PREFIXES)
def test_guard_raises_when_a_forbidden_module_is_loaded(monkeypatch, forbidden_module_name):
    monkeypatch.setitem(sys.modules, forbidden_module_name, types.ModuleType(forbidden_module_name))
    with pytest.raises(RuntimeError, match=forbidden_module_name.replace(".", r"\.")):
        assert_no_forbidden_modules_loaded()


def test_guard_raises_for_a_submodule_of_a_forbidden_prefix(monkeypatch):
    monkeypatch.setitem(sys.modules, "core.oms.order_router", types.ModuleType("core.oms.order_router"))
    with pytest.raises(RuntimeError, match="core.oms.order_router"):
        assert_no_forbidden_modules_loaded()


def test_guard_is_a_noop_when_no_forbidden_module_is_loaded():
    assert_no_forbidden_modules_loaded()  # must not raise


@pytest.mark.parametrize("near_miss_module_name", NEAR_MISS_NAMES)
def test_guard_does_not_flag_a_near_miss_module_name(monkeypatch, near_miss_module_name):
    monkeypatch.setitem(sys.modules, near_miss_module_name, types.ModuleType(near_miss_module_name))
    assert_no_forbidden_modules_loaded()  # must not raise


def test_near_miss_names_line_up_one_to_one_with_forbidden_prefixes_plus_dunder_main():
    # One near-miss per FORBIDDEN_PREFIXES entry, plus "__main__" (Section 4
    # of docs/architecture/equity_intel_boundary_decision.md).
    assert len(NEAR_MISS_NAMES) == len(FORBIDDEN_PREFIXES) + 1


def test_scan_pipeline_has_no_order_or_position_method():
    members = {name for name, _ in inspect.getmembers(ScanPipeline)}
    forbidden_substrings = ("order", "position", "broker", "execute_trade", "place")
    for name in members:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), name


def test_scan_pipeline_run_stops_at_the_first_blocked_stage_without_any_trading_call():
    # This legacy scoring shell is intentionally not wired to the E1-E3
    # acquisition entry point and remains blocked before any trading call.
    pipeline = ScanPipeline()
    try:
        pipeline.run()
        assert False, "expected NotImplementedError at the first blocked stage"
    except NotImplementedError as exc:
        assert "BLOCKED" in str(exc)

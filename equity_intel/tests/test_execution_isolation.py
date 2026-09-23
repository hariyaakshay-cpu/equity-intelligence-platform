"""Execution-isolation tests -- structural, not trading tests.

These prove that Equity Intelligence has no order-submission path, does
not instantiate the paper trading engine, does not access OMS execution
services, and does not import broker adapters. No order (paper or live) is
placed by any test in this module.
"""
import inspect

from core.oms.execution_mode import ExecutionMode
from equity_intel.scanner.execution_guard import assert_not_live
from equity_intel.scanner.shell import ScanPipeline


def test_assert_not_live_raises_for_live_mode_without_redeclaring_process_mode():
    try:
        assert_not_live(ExecutionMode.LIVE)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "LIVE" in str(exc)


def test_assert_not_live_is_a_noop_for_non_live_modes():
    for mode in (ExecutionMode.TEST, ExecutionMode.PAPER, ExecutionMode.SHADOW):
        assert_not_live(mode)  # must not raise


def test_scan_pipeline_has_no_order_or_position_method():
    members = {name for name, _ in inspect.getmembers(ScanPipeline)}
    forbidden_substrings = ("order", "position", "broker", "execute_trade", "place")
    for name in members:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), name


def test_scan_pipeline_run_stops_at_the_first_blocked_stage_without_any_trading_call():
    # The pipeline stops at load_universe (B3), the first stage, since no
    # universe source is selected -- it never reaches a trading call.
    pipeline = ScanPipeline()
    try:
        pipeline.run()
        assert False, "expected NotImplementedError at the first blocked stage"
    except NotImplementedError as exc:
        assert "BLOCKED" in str(exc)

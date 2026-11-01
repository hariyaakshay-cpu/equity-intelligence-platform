"""Synthetic-data tests for the round-3 setups (no real market data, no network)."""
from datetime import datetime, timedelta

from equity_intel.intraday.round3 import (breadth_orb_long, market_context, rs_leader_long, run_round3,
                                          volume_baseline, volume_surge_long)
from equity_intel.intraday.setups import Bar


def _bars(day="2026-01-05", n=75, base=100.0, vol=1000.0, overrides=None):
    start = datetime.fromisoformat(f"{day}T09:15:00+05:30")
    bars = []
    for i in range(n):
        o = h = l = c = base
        v = vol
        if overrides and i in overrides:
            o, h, l, c, v = overrides[i]
        bars.append(Bar(start + timedelta(minutes=5 * i), o, h, l, c, v))
    return bars


def test_market_context_needs_enough_stocks():
    sessions = {f"S{k}": {"2026-01-02": _bars("2026-01-02"), "2026-01-05": _bars("2026-01-05", base=101.0)}
                for k in range(60)}
    ctx = market_context(sessions)
    breadth, med = ctx["2026-01-05"][10]
    assert breadth == 1.0 and abs(med - 0.01) < 1e-9
    assert market_context({"S0": sessions["S0"]})["2026-01-05"][10] is None


def test_breadth_orb_blocks_weak_market():
    # bar 1 gives the opening range a width (99.5-100.5); bar 3 closes above its high
    bars = _bars(overrides={1: (100, 100.5, 99.5, 100, 1000), 3: (100, 101, 100, 101, 1000)})
    weak = [(0.4, 0.0)] * 75
    strong = [(0.7, 0.005)] * 75
    assert breadth_orb_long(bars, weak) is None
    assert breadth_orb_long(bars, strong) == 3


def test_rs_leader_needs_margin_and_window():
    bars = _bars(overrides={12: (101.5, 102, 101.5, 102, 1000)})  # bar 12 closes 10:15
    ctx = [(0.5, 0.0)] * 75
    assert rs_leader_long(bars, 100.0, ctx) == 12
    assert rs_leader_long(bars, 100.0, [(0.5, 0.012)] * 75) is None  # median too strong: no margin


def test_volume_surge_needs_3x_and_breakout():
    days = {f"2025-12-{k:02d}": _bars(f"2025-12-{k:02d}") for k in range(1, 22)}
    days["2026-01-05"] = _bars(overrides={10: (100, 102, 100, 102, 3500)})
    dates = sorted(days)
    base = volume_baseline(days, dates, len(dates) - 1)
    assert volume_surge_long(days["2026-01-05"], base) == 10
    assert volume_surge_long(_bars(overrides={10: (100, 102, 100, 102, 2500)}), base) is None
    assert volume_baseline(days, dates, 5) is None  # fewer than 20 prior sessions


def test_run_round3_rejects_unknown_setup():
    sessions = {"S0": {"2026-01-02": _bars("2026-01-02"), "2026-01-05": _bars("2026-01-05")}}
    ctx = market_context(sessions, min_stocks=1)
    try:
        run_round3("NOPE", sessions, ctx)
        assert False
    except ValueError:
        pass

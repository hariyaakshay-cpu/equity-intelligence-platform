"""Research backtest for the pre-registered intraday setups. Read-only; no orders, no DB writes.

Evaluation convention (research only; the product emits NO entry/stop/target, D5):
entry = OPEN of the bar after the trigger bar; exit = CLOSE of the last bar starting at or before
15:15 (same-session square off, D1). Costs: see COSTS (ASSUMED, re-verify before relying on them).
Acceptance thresholds are the D6 values recorded in the spec; drawdown limit fixed 2026-10-25.
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import time
from typing import Dict, List, Sequence

from equity_intel.intraday.setups import Bar, find_trigger

EXIT_LAST_START = time(15, 15)
MAX_SIGNALS_PER_DAY = 5

# ASSUMED public Upstox/NSE equity-intraday schedule. NOT verified against current circulars.
COSTS = {
    "brokerage_cap": 20.0, "brokerage_pct": 0.0005,
    "stt_sell_pct": 0.00025, "txn_pct": 0.0000297, "sebi_pct": 0.000001,
    "stamp_buy_pct": 0.00003, "gst_pct": 0.18, "slippage_pct_per_side": 0.0005,
}
NOTIONAL = 100_000.0

# D6 + 2026-10-25 additions.
THRESHOLDS = {"min_trades": 300, "min_sessions": 60, "max_symbol_profit_share": 0.10,
              "max_drawdown_pct_points": 20.0}


def round_trip_cost_pct(notional: float = NOTIONAL, c: Dict = COSTS) -> float:
    brok = 2 * min(c["brokerage_cap"], c["brokerage_pct"] * notional)
    txn = 2 * c["txn_pct"] * notional
    other = c["stt_sell_pct"] * notional + c["sebi_pct"] * 2 * notional + c["stamp_buy_pct"] * notional
    gst = c["gst_pct"] * (brok + txn)
    slip = 2 * c["slippage_pct_per_side"] * notional
    return (brok + txn + other + gst + slip) / notional * 100.0


def trade_for(bars: Sequence[Bar], trig: int):
    if trig + 1 >= len(bars):
        return None
    entry = bars[trig + 1].o
    exits = [b for b in bars[trig + 1:] if b.ts.time() <= EXIT_LAST_START]
    if not exits or entry <= 0:
        return None
    exit_px = exits[-1].c
    gross = (exit_px / entry - 1.0) * 100.0
    return {"trigger_ts": bars[trig].ts.isoformat(), "gross_pct": gross, "net_pct": gross - round_trip_cost_pct()}


def run_setup(setup: str, sessions: Dict[str, Dict[str, Sequence[Bar]]]) -> List[dict]:
    """sessions[symbol][YYYY-MM-DD] -> closed bars. Previous-session context taken from the same dict
    (previous available session of that symbol; the verified NSE calendar is still required for the product)."""
    per_day: Dict[str, list] = defaultdict(list)
    for sym, days in sessions.items():
        dates = sorted(days)
        for k, d in enumerate(dates):
            bars = days[d]
            prev = days[dates[k - 1]] if k else None
            prev_close = prev[-1].c if prev else None
            prev_high = max(b.h for b in prev) if prev else None
            trig = find_trigger(setup, bars, prev_close, prev_high)
            if trig is None:
                continue
            t = trade_for(bars, trig)
            if t:
                t.update(symbol=sym, date=d)
                per_day[d].append(t)
    trades = []
    for d in sorted(per_day):
        ranked = sorted(per_day[d], key=lambda t: (t["trigger_ts"], t["symbol"]))  # P6
        trades.extend(ranked[:MAX_SIGNALS_PER_DAY])
    return trades


def evaluate(trades: Sequence[dict], boots: int = 2000, seed: int = 1) -> dict:
    n = len(trades)
    out = {"trades": n, "sessions": len({t["date"] for t in trades}),
           "round_trip_cost_pct": round(round_trip_cost_pct(), 4)}
    if not n:
        out["verdict"] = "NO_TRADES"
        return out
    net = [t["net_pct"] for t in trades]
    out["mean_net_pct"] = sum(net) / n
    out["win_rate"] = sum(1 for x in net if x > 0) / n
    by_date: Dict[str, list] = defaultdict(list)
    for t in trades:
        by_date[t["date"]].append(t["net_pct"])
    dates = sorted(by_date)
    rng = random.Random(seed)
    means = []
    for _ in range(boots):
        s = c = 0
        for _ in dates:
            xs = by_date[dates[rng.randrange(len(dates))]]
            s += sum(xs); c += len(xs)
        means.append(s / c)
    means.sort()
    out["ci95_mean_net_pct"] = [means[int(0.025 * boots)], means[int(0.975 * boots) - 1]]
    prof: Dict[str, float] = defaultdict(float)
    for t in trades:
        prof[t["symbol"]] += t["net_pct"]
    total = sum(prof.values())
    out["top_symbol_profit_share"] = (max(prof.values()) / total) if total > 0 else None
    eq = peak = dd = 0.0
    for d in dates:
        eq += sum(by_date[d])
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    out["max_drawdown_pct_points"] = dd
    th = THRESHOLDS
    checks = {
        "min_trades": n >= th["min_trades"],
        "min_sessions": out["sessions"] >= th["min_sessions"],
        "expectancy_positive": out["mean_net_pct"] > 0,
        "bootstrap_ci_above_zero": out["ci95_mean_net_pct"][0] > 0,
        "symbol_concentration": out["top_symbol_profit_share"] is not None
                                 and out["top_symbol_profit_share"] <= th["max_symbol_profit_share"],
        "max_drawdown": dd <= th["max_drawdown_pct_points"],
    }
    out["checks"] = checks
    out["not_computed"] = ["sector_concentration (no sector data wired)", "walk-forward split (single full-period run)"]
    out["verdict"] = "PASS_STAGE4_CANDIDATE" if all(checks.values()) else "FAIL"
    return out

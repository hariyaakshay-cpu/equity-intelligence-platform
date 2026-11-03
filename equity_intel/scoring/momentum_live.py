"""Today's 12-1 momentum list for the dashboard. Pure functions, no I/O.

Uses exactly the frozen rule of docs/architecture/equity_intel_momentum_12_1_preregistration.md (constants imported
from momentum_12_1, not copied), evaluated at the latest bar instead of historically. NOT VALIDATED: the rule failed its
DEV test narrowly on 2026-11-03 (gross excess +0.30%, net -0.05% per 21 sessions). No target, no stop-loss.
"""
from __future__ import annotations

from statistics import median
from typing import Dict, List, Sequence, Tuple

from equity_intel.scoring import momentum_12_1 as rule

STATUS = "NOT VALIDATED - failed DEV test narrowly (3 Nov 2026) - research only - not trade advice"


def latest_list(series: Dict[str, Tuple[Sequence[str], Sequence[float], Sequence[float], Sequence[float]]],
                asof: str) -> dict:
    """series: {symbol: (dates, o, c, v)}. Only symbols whose last bar is `asof` take part (stale files skipped)."""
    eligible, stale, short, illiquid, excluded = [], 0, 0, 0, []
    for sym in sorted(series):
        dates, _o, c, v = series[sym]
        if not dates or dates[-1] != asof:
            stale += 1
            continue
        k = len(c) - 1
        if k < rule.LOOKBACK or c[k - rule.LOOKBACK] <= 0:
            short += 1
            continue
        tv = median(c[i] * v[i] for i in range(k - rule.LIQ_WINDOW + 1, k + 1))
        if tv < rule.MIN_TRADED_VALUE:
            illiquid += 1
            continue
        row = {"symbol": sym, "score_pct": 100 * (c[k - rule.SKIP] / c[k - rule.LOOKBACK] - 1.0),
               "close": c[k], "traded_value_cr": tv / 1e7}
        if any(c[i - 1] > 0 and abs(c[i] / c[i - 1] - 1.0) > rule.BREAK_MOVE for i in range(k - rule.LOOKBACK + 1, k + 1)):
            excluded.append(sym)
            row["excluded"] = True
        eligible.append(row)
    ranked = sorted(eligible, key=lambda r: (-r["score_pct"], r["symbol"]))
    picks = [r for r in ranked if not r.get("excluded")][:rule.TOP_N] if len(eligible) >= rule.MIN_ELIGIBLE else []
    for i, r in enumerate(picks, 1):
        r["rank"] = i
    return {"asof": asof, "status": STATUS, "hold_sessions": rule.HOLD, "top_n": rule.TOP_N,
            "eligible": len(eligible), "min_eligible": rule.MIN_ELIGIBLE, "skipped_stale": stale,
            "skipped_short_history": short, "skipped_illiquid": illiquid, "corporate_action_flagged": excluded,
            "picks": picks}

"""12-1 month momentum study (docs/architecture/equity_intel_momentum_12_1_preregistration.md). Pure functions, no I/O.

series: {symbol: (dates, o, c, v)} with equal-length lists in date order.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Dict, List, Sequence, Tuple

from equity_intel.scoring.daily_eval import block_bootstrap_means, quantile

LOOKBACK, SKIP, HOLD = 252, 21, 21
TOP_N = 10
MIN_TRADED_VALUE = 1e8
LIQ_WINDOW = 20
BREAK_MOVE = 0.30
COST = 0.0035
MIN_ELIGIBLE = 100
LOWER_Q = 0.025
MIN_DATES = 100
MAX_SYMBOL_SHARE = 0.10


def symbol_rows(symbol: str, dates: Sequence[str], o: Sequence[float], c: Sequence[float], v: Sequence[float]) -> List[dict]:
    n = len(c)
    big = [i > 0 and c[i - 1] > 0 and abs(c[i] / c[i - 1] - 1.0) > BREAK_MOVE for i in range(n)]
    out = []
    for k in range(LOOKBACK, n - HOLD):
        if c[k - LOOKBACK] <= 0 or o[k + 1] <= 0:
            continue
        out.append({
            "date": dates[k], "exit_date": dates[k + HOLD], "symbol": symbol,
            "score": c[k - SKIP] / c[k - LOOKBACK] - 1.0,
            "traded_value": median(c[i] * v[i] for i in range(k - LIQ_WINDOW + 1, k + 1)),
            "ret": c[k + HOLD] / o[k + 1] - 1.0,
            "excl": any(big[k - LOOKBACK:k + HOLD + 1]),
        })
    return out


def cohorts(rows: Sequence[dict], keep_date, index_ret: Dict[str, float] = None) -> dict:
    by_date: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        if r["traded_value"] >= MIN_TRADED_VALUE and keep_date(r):
            by_date[r["date"]].append(r)
    out, dropped = [], 0
    for d in sorted(by_date):
        elig = by_date[d]
        if len(elig) < MIN_ELIGIBLE:
            continue
        bench = [r["ret"] for r in elig if not r["excl"]]
        picks = sorted(elig, key=lambda r: (-r["score"], r["symbol"]))[:TOP_N]
        kept = [(r["symbol"], r["ret"]) for r in picks if not r["excl"]]
        dropped += len(picks) - len(kept)
        if not kept or not bench:
            continue
        g, b = sum(x for _, x in kept) / len(kept), sum(bench) / len(bench)
        c = {"date": d, "n": len(kept), "gross": g, "bench": b, "excess": g - COST - b, "picks": kept}
        if index_ret and d in index_ret:
            c["excess_index"] = g - COST - index_ret[d]
        out.append(c)
    return {"cohorts": out, "excluded_picks": dropped}


def summarize(res: dict) -> dict:
    cs = res["cohorts"]
    if not cs:
        return {"signal_dates": 0, "verdict": "FAIL", "dev_qualifies_for_holdout": False}
    ex = [c["excess"] for c in cs]
    mean = sum(ex) / len(ex)
    boot = block_bootstrap_means(ex, HOLD)
    sym = defaultdict(float)
    for c in cs:
        for s, r in c["picks"]:
            sym[s] += (r - COST - c["bench"]) / c["n"]
    total = sum(ex)
    top = max(sym.items(), key=lambda kv: kv[1])
    share = top[1] / total if total > 0 else None
    cur = peak = mdd = 0.0
    for e in ex:
        cur += e; peak = max(peak, cur); mdd = max(mdd, peak - cur)
    exi = [c["excess_index"] for c in cs if "excess_index" in c]
    checks = {"mean_net_excess_positive": mean > 0, "bootstrap_lower_above_zero": quantile(boot, LOWER_Q) > 0,
              "min_signal_dates": len(cs) >= MIN_DATES,
              "symbol_concentration": share is not None and share <= MAX_SYMBOL_SHARE}
    return {"signal_dates": len(cs), "first_date": cs[0]["date"], "last_date": cs[-1]["date"],
            "mean_picks": sum(c["n"] for c in cs) / len(cs),
            "mean_gross_pct": 100 * sum(c["gross"] for c in cs) / len(cs),
            "mean_net_pct": 100 * (sum(c["gross"] for c in cs) / len(cs) - COST),
            "mean_bench_pct": 100 * sum(c["bench"] for c in cs) / len(cs),
            "mean_net_excess_pct": 100 * mean,
            "mean_gross_excess_pct": 100 * (mean + COST),
            "mean_net_excess_vs_index_pct": 100 * sum(exi) / len(exi) if exi else None,
            "share_dates_excess_positive": sum(e > 0 for e in ex) / len(ex),
            "bootstrap_lower_pct": 100 * quantile(boot, LOWER_Q), "bootstrap_upper_pct": 100 * quantile(boot, 1 - LOWER_Q),
            "top_symbol": top[0], "top_symbol_profit_share": share,
            "max_drawdown_cum_excess_pct_points": 100 * mdd, "excluded_picks": res["excluded_picks"],
            "checks": checks, "dev_qualifies_for_holdout": mean > 0,
            "verdict": "PASS" if all(checks.values()) else "FAIL"}

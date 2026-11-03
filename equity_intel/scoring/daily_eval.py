"""Evaluation for the daily/swing pre-registration
(docs/architecture/equity_intel_daily_signals_preregistration_DRAFT.md; interpretation notes in
research/daily/evaluation_decisions_2026-11-03.md, both written before any result). Pure functions, no I/O.

rows: dicts from scripts/equity_daily_replay.py (date, symbol, short, medium, traded_value, ret5, excl5, ret20, excl20).
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List, Optional, Sequence

LISTS = {"short": 5, "medium": 20}
CUTOFF = 70
TOP_N = 10
MIN_TRADED_VALUE = 1e8          # INR 10 crore
COST = 0.0035                   # assumed delivery round trip, picks only
BOOT_N = 10000
BOOT_SEED = 20261103
LOWER_Q = 0.0125                # two-sided 97.5% interval (alpha 0.05 / 2 lists)
MIN_DATES = 100
MAX_SYMBOL_SHARE = 0.10


def _f(x) -> Optional[float]:
    if x is None or x == "":
        return None
    return float(x)


def cohorts(rows: Sequence[dict], name: str, index_ret: Optional[Dict[str, float]] = None) -> dict:
    """Per signal date: picks, gross/net cohort return, benchmark, excess. Dates with no kept pick give no cohort."""
    hold = LISTS[name]
    by_date: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    out, excluded_picks, excluded_bench = [], 0, 0
    for d in sorted(by_date):
        elig = []
        for r in by_date[d]:
            tv, ret = _f(r["traded_value"]), _f(r.get(f"ret{hold}"))
            if tv is None or tv < MIN_TRADED_VALUE or ret is None:
                continue
            elig.append((r, ret, int(float(r.get(f"excl{hold}") or 0))))
        bench = [ret for r, ret, ex in elig if not ex]
        excluded_bench += sum(1 for _, _, ex in elig if ex)
        cand = [(int(float(r[name])), r["symbol"], ret, ex) for r, ret, ex in elig
                if r.get(name) not in (None, "") and float(r[name]) >= CUTOFF]
        cand.sort(key=lambda x: (-x[0], x[1]))
        picks = cand[:TOP_N]
        kept = [(s, ret) for _, s, ret, ex in picks if not ex]
        excluded_picks += len(picks) - len(kept)
        if not kept or not bench:
            continue
        gross = sum(ret for _, ret in kept) / len(kept)
        b = sum(bench) / len(bench)
        c = {"date": d, "n": len(kept), "gross": gross, "net": gross - COST, "bench": b,
             "excess": gross - COST - b, "picks": kept}
        if index_ret is not None and d in index_ret:
            c["excess_index"] = gross - COST - index_ret[d]
        out.append(c)
    return {"cohorts": out, "excluded_picks": excluded_picks, "excluded_bench_rows": excluded_bench}


def block_bootstrap_means(x: Sequence[float], block: int, n: int = BOOT_N, seed: int = BOOT_SEED) -> List[float]:
    """Circular moving-block bootstrap of the mean, blocks over consecutive signal dates."""
    m = len(x)
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        tot, k = 0.0, 0
        while k < m:
            s = rng.randrange(m)
            for j in range(min(block, m - k)):
                tot += x[(s + j) % m]
            k += min(block, m - k)
        means.append(tot / m)
    means.sort()
    return means


def quantile(sorted_vals: Sequence[float], q: float) -> float:
    i = min(len(sorted_vals) - 1, max(0, int(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def summarize(res: dict, name: str) -> dict:
    hold = LISTS[name]
    cs = res["cohorts"]
    ex = [c["excess"] for c in cs]
    if not cs:
        return {"list": name, "signal_dates": 0, "verdict": "FAIL", "reason": "no cohorts"}
    mean = sum(ex) / len(ex)
    boot = block_bootstrap_means(ex, block=hold)
    sym = defaultdict(float)
    for c in cs:
        for s, ret in c["picks"]:
            sym[s] += (ret - COST - c["bench"]) / c["n"]
    total = sum(ex)
    top_sym, top_val = max(sym.items(), key=lambda kv: kv[1])
    share = top_val / total if total > 0 else None
    curve, peak, mdd = 0.0, 0.0, 0.0
    for e in ex:
        curve += e
        peak = max(peak, curve)
        mdd = max(mdd, peak - curve)
    exi = [c["excess_index"] for c in cs if "excess_index" in c]
    checks = {
        "mean_net_excess_positive": mean > 0,
        "bootstrap_lower_above_zero": quantile(boot, LOWER_Q) > 0,
        "min_signal_dates": len(cs) >= MIN_DATES,
        "symbol_concentration": share is not None and share <= MAX_SYMBOL_SHARE,
    }
    return {
        "list": name, "hold_sessions": hold, "signal_dates": len(cs),
        "mean_picks": sum(c["n"] for c in cs) / len(cs),
        "mean_gross_pct": 100 * sum(c["gross"] for c in cs) / len(cs),
        "mean_net_pct": 100 * sum(c["net"] for c in cs) / len(cs),
        "mean_bench_pct": 100 * sum(c["bench"] for c in cs) / len(cs),
        "mean_net_excess_pct": 100 * mean,
        "mean_net_excess_vs_index_pct": 100 * sum(exi) / len(exi) if exi else None,
        "share_dates_excess_positive": sum(1 for e in ex if e > 0) / len(ex),
        "bootstrap_lower_pct": 100 * quantile(boot, LOWER_Q),
        "bootstrap_upper_pct": 100 * quantile(boot, 1 - LOWER_Q),
        "top_symbol": top_sym, "top_symbol_profit_share": share,
        "max_drawdown_cum_excess_pct_points": 100 * mdd,
        "excluded_picks": res["excluded_picks"], "excluded_bench_rows": res["excluded_bench_rows"],
        "checks": checks,
        "dev_qualifies_for_holdout": mean > 0,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
    }

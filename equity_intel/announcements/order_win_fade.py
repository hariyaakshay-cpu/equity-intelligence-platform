"""Order-win fade study (docs/architecture/order_win_fade_preregistration.md). Pure functions, no I/O.

Takes the observations built by the unchanged v2.1 pipeline and applies only
the frozen fade rules: H0, materiality >= 5%, entry 2023-01-01..2026-10-31,
EQ series, no locked-low entry; short returns = minus the long returns;
flat 0.50% round trip; one test (K = 1).
"""
from __future__ import annotations

from collections import Counter
from datetime import date

import pandas as pd

from equity_intel.announcements.event_study import bootstrap_lower

PERIOD = (date(2023, 1, 1), date(2026, 10, 31))
THRESHOLD = 0.05
HORIZON = "H0"
COST = 0.005
MIN_N = 100
MIN_SESSIONS = 40
MAX_SYMBOL_SHARE = 0.10
CONFIDENCE = 0.95
SEED = 20261118
N_BOOT = 10_000


def fade_observations(obs: pd.DataFrame, prices: dict, series: dict) -> tuple[pd.DataFrame, Counter]:
    """Filter v2.1 observations to the fade sample and add short-side returns."""
    drops: Counter = Counter()
    d = obs[(obs["horizon"] == HORIZON) & (obs["materiality"] >= THRESHOLD)]
    d = d[(d["entry"] >= PERIOD[0]) & (d["entry"] <= PERIOD[1])]
    rows = []
    for r in d.itertuples(index=False):
        if series.get(r.symbol) != "EQ":
            drops["not_eq_series"] += 1
            continue
        e = prices[r.symbol].loc[r.entry]
        if e["o"] == e["l"] == e["c"]:
            drops["locked_low_entry"] += 1
            continue
        short_raw, short_abn = -r.raw, -r.abn
        rows.append({"symbol": r.symbol, "entry": r.entry, "amt_cr": r.amt_cr,
                     "mcap_cr": r.mcap_cr, "materiality": r.materiality,
                     "short_raw": short_raw, "short_abn": short_abn,
                     "net_short_raw": short_raw - COST, "net_short_abn": short_abn - COST,
                     "big_move": r.big_move, "ts_source": r.ts_source})
    return pd.DataFrame(rows), drops


def evaluate_fade(d: pd.DataFrame) -> dict:
    """The single frozen verdict."""
    n = len(d)
    if n == 0:
        return {"n": 0, "sessions": 0, "verdict": "INSUFFICIENT_DATA"}
    sessions = int(d["entry"].nunique())
    mean_abn = float(d["net_short_abn"].mean())
    mean_raw = float(d["net_short_raw"].mean())
    lower = bootstrap_lower(d["net_short_abn"], d["entry"], CONFIDENCE, n_boot=N_BOOT, seed=SEED)
    total = d["net_short_abn"].sum()
    share = float(d.groupby("symbol")["net_short_abn"].sum().max() / total) if total > 0 else float("nan")
    if n < MIN_N or sessions < MIN_SESSIONS:
        verdict = "INSUFFICIENT_DATA"
    else:
        ok = mean_abn > 0 and mean_raw > 0 and lower > 0 and share <= MAX_SYMBOL_SHARE
        verdict = "PASS" if ok else "FAIL"
    return {"n": n, "sessions": sessions, "symbols": int(d["symbol"].nunique()),
            "mean_net_short_abn_pct": mean_abn * 100, "mean_net_short_raw_pct": mean_raw * 100,
            "lower_bound_pct": lower * 100, "max_symbol_share": share,
            "win_rate_net_short_raw": float((d["net_short_raw"] > 0).mean()),
            "big_moves": int(d["big_move"].sum()), "verdict": verdict}

"""Point-in-time replay of PROVISIONAL scoring v0 over daily history (see
docs/architecture/equity_intel_daily_signals_preregistration_DRAFT.md). Pure functions, no I/O, no network.

For signal date t it feeds the SAME feature and scoring code the live scan uses with exactly the trailing
252 bars ending at t (the live acquisition stores 252 bars per symbol), so no bar after t can influence a score.
Forward return = close of session t+H over the OPEN of session t+1.
"""
from __future__ import annotations

from statistics import median
from typing import Dict, List, Sequence

from equity_intel.contracts.quality import DataStatus
from equity_intel.features.compute import compute_instrument
from equity_intel.features.config import IndicatorConfig
from equity_intel.scoring.components_v0 import horizon_scores

WINDOW = 252
HOLDS = {"short": 5, "medium": 20}
LIQUIDITY_WINDOW = 20
BREAK_LOOKBACK = 60
BREAK_MOVE = 0.30


def replay_symbol(symbol: str, dates: Sequence[str], o: Sequence[float], h: Sequence[float], l: Sequence[float],
                  c: Sequence[float], v: Sequence[float], benchmark: Dict[str, float], cfg: IndicatorConfig) -> List[dict]:
    n = len(c)
    big = [i > 0 and c[i - 1] > 0 and abs(c[i] / c[i - 1] - 1.0) > BREAK_MOVE for i in range(n)]
    rows: List[dict] = []
    for k in range(WINDOW - 1, n - 1):  # k+1 must exist for the entry open
        sl = slice(k - WINDOW + 1, k + 1)
        quality, features, _ = compute_instrument(symbol, h[sl], l[sl], c[sl], v[sl], cfg, dates=dates[sl], benchmark=benchmark)
        if quality.status is not DataStatus.VALID:
            continue
        scores = horizon_scores(features)
        if scores["short"] is None and scores["medium"] is None:
            continue
        row = {"date": dates[k], "symbol": symbol, "short": scores["short"], "medium": scores["medium"],
               "traded_value": median(c[i] * v[i] for i in range(k - LIQUIDITY_WINDOW + 1, k + 1))}
        for name, hold in HOLDS.items():
            if k + hold < n and o[k + 1] > 0:
                row[f"ret{hold}"] = c[k + hold] / o[k + 1] - 1.0
                row[f"excl{hold}"] = int(any(big[max(0, k - BREAK_LOOKBACK):k + hold + 1]))
        rows.append(row)
    return rows

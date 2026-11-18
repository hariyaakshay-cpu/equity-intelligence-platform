"""Order-win event study v2.

Implements docs/architecture/order_win_event_study_preregistration.md exactly.
Pure functions: no network, no database, no orders.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date

import numpy as np
import pandas as pd

from equity_intel.announcements.event_study import (bootstrap_lower,
                                                     entry_session)

ORDER = re.compile(r"\b(orders?|contracts?|LOA|LOI|letter of (award|acceptance|intent)"
                   r"|work order|purchase order)\b", re.I)
WIN = re.compile(r"\b(receiv\w*|bag\w*|secur\w*|win|wins|won|award\w*)\b", re.I)
NEG = re.compile(r"\b(tax|gst|demand|penalty|commissioner|tribunal|court|sebi order"
                 r"|show cause|assessment)\b", re.I)
AMOUNT = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\b|lakhs?|lacs?)", re.I)

HORIZONS = {"H0": 0, "H5": 5, "H20": 20}
COST = 0.005
NON_OVERLAP = 20
PRIMARY, SECONDARY = 0.05, (0.02, 0.10)
EVENT_LIQ_MIN, BENCH_LIQ_MIN = 2e7, 1e8          # INR 2 crore, INR 10 crore
LIQ_WINDOW, LIQ_MIN_ROWS = 20, 15
DEV = (date(2014, 1, 1), date(2022, 12, 31))
HOLDOUT = (date(2023, 1, 1), date(2026, 10, 31))
MIN_DEV_OBS, MIN_DEV_SESSIONS, MIN_HOLDOUT_OBS = 300, 60, 100
MAX_SYMBOL_SHARE = 0.10
K_TESTS = 3
BIG_MOVE = 0.20


def parse_amount_cr(text) -> float | None:
    """Order value in INR crore from the first rupee amount, else None."""
    m = AMOUNT.search(str(text or ""))
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    if value <= 0:
        return None
    return value if m.group(2).lower().startswith("cr") else value / 100.0


def is_order_win(text) -> bool:
    s = str(text or "")
    return bool(ORDER.search(s) and WIN.search(s) and not NEG.search(s)
                and parse_amount_cr(s) is not None)


def extract_order_wins(ann: pd.DataFrame) -> pd.DataFrame:
    mask = ann["text"].map(is_order_win)
    out = ann[mask].copy()
    out["amt_cr"] = out["text"].map(parse_amount_cr)
    return out.reset_index(drop=True)


def period_of(d: date) -> str:
    if DEV[0] <= d <= DEV[1]:
        return "dev"
    if HOLDOUT[0] <= d <= HOLDOUT[1]:
        return "holdout"
    return "other"


def build_units(wins: pd.DataFrame, sessions: list[date]) -> tuple[pd.DataFrame, Counter]:
    """(symbol, entry) units with the largest amount, then per-symbol non-overlap."""
    drops: Counter = Counter()
    pos = {s: i for i, s in enumerate(sessions)}
    rows = []
    for r in wins.itertuples(index=False):
        e = entry_session(r.event_ts, sessions)
        if e is None:
            drops["no_entry_session"] += 1
            continue
        rows.append((r.symbol, e, r.amt_cr, r.ts_source))
    if not rows:
        return pd.DataFrame(columns=["symbol", "entry", "amt_cr", "ts_source"]), drops
    u = (pd.DataFrame(rows, columns=["symbol", "entry", "amt_cr", "ts_source"])
         .sort_values(["symbol", "entry", "amt_cr"], ascending=[True, True, False])
         .drop_duplicates(["symbol", "entry"]))
    kept = []
    for sym, g in u.groupby("symbol", sort=True):
        last = None
        for r in g.itertuples(index=False):
            if last is not None and pos[r.entry] - pos[last] <= NON_OVERLAP:
                drops["overlap"] += 1
                continue
            kept.append(r)
            last = r.entry
    return pd.DataFrame(kept, columns=u.columns).reset_index(drop=True), drops


def _median_value(px: pd.DataFrame, prior: list[date]) -> float | None:
    rows = px.reindex(prior).dropna(subset=["c", "v"])
    if len(rows) < LIQ_MIN_ROWS:
        return None
    return float((rows["c"] * rows["v"]).median())


class EqualWeightBenchmark:
    """Equal-weight open->close return of liquid stocks over (entry, exit)."""

    def __init__(self, universe: dict[str, pd.DataFrame], sessions: list[date]):
        idx = pd.Index(sessions)
        self.o = pd.DataFrame({s: p["o"] for s, p in universe.items()}).reindex(idx)
        self.c = pd.DataFrame({s: p["c"] for s, p in universe.items()}).reindex(idx)
        value = self.c * pd.DataFrame({s: p["v"] for s, p in universe.items()}).reindex(idx)
        self.liq = (value.shift(1).rolling(LIQ_WINDOW, min_periods=LIQ_MIN_ROWS)
                    .median() >= BENCH_LIQ_MIN)
        self._cache: dict = {}

    def ret(self, entry: date, exit_: date) -> float:
        key = (entry, exit_)
        if key not in self._cache:
            r = (self.c.loc[exit_] / self.o.loc[entry] - 1.0)[self.liq.loc[entry]].dropna()
            self._cache[key] = float(r.mean()) if len(r) else float("nan")
        return self._cache[key]


def build_observations(units: pd.DataFrame, prices: dict, index: pd.DataFrame,
                       bench: EqualWeightBenchmark, shares: dict, sessions: list[date]
                       ) -> tuple[pd.DataFrame, Counter]:
    drops: Counter = Counter()
    pos = {s: i for i, s in enumerate(sessions)}
    rows = []
    for u in units.itertuples(index=False):
        px = prices.get(u.symbol)
        if px is None:
            drops["no_price_file"] += 1
            continue
        n_sh = shares.get(u.symbol)
        if not n_sh:
            drops["no_shares"] += 1
            continue
        i = pos[u.entry]
        prior = sessions[max(0, i - LIQ_WINDOW):i]
        val = _median_value(px, prior)
        if val is None or val < EVENT_LIQ_MIN:
            drops["illiquid"] += 1
            continue
        if u.entry not in px.index or u.entry not in index.index or i == 0 \
                or sessions[i - 1] not in px.index:
            drops["missing_entry_row"] += 1
            continue
        e = px.loc[u.entry]
        if e["o"] == e["h"] == e["c"]:
            drops["locked_entry"] += 1
            continue
        mcap_cr = n_sh * px.loc[sessions[i - 1], "c"] / 1e7
        mat = u.amt_cr / mcap_cr
        for hz, k in HORIZONS.items():
            if i + k >= len(sessions):
                drops[f"{hz}:no_exit_session"] += 1
                continue
            ex = sessions[i + k]
            if ex not in px.index or ex not in index.index:
                drops[f"{hz}:missing_exit_row"] += 1
                continue
            raw = px.loc[ex, "c"] / e["o"] - 1.0
            ew = bench.ret(u.entry, ex)
            idx_r = index.loc[ex, "c"] / index.loc[u.entry, "o"] - 1.0
            rows.append({"symbol": u.symbol, "entry": u.entry, "exit": ex, "horizon": hz,
                         "amt_cr": u.amt_cr, "mcap_cr": mcap_cr, "materiality": mat,
                         "raw": raw, "abn": raw - ew, "abn_index": raw - idx_r,
                         "net_raw": raw - COST, "net_abn": raw - ew - COST,
                         "net_abn_index": raw - idx_r - COST, "ts_source": u.ts_source,
                         "big_move": abs(raw) > BIG_MOVE, "period": period_of(u.entry)})
    return pd.DataFrame(rows), drops


def summarise(d: pd.DataFrame, phase: str, confidence: float) -> dict:
    n = len(d)
    if n == 0:
        return {"n": 0, "sessions": 0, "verdict": "INSUFFICIENT_DATA" if phase == "dev" else "FAIL"}
    mean_abn, mean_raw = float(d["net_abn"].mean()), float(d["net_raw"].mean())
    lower = bootstrap_lower(d["net_abn"], d["entry"], confidence)
    total = d["net_abn"].sum()
    share = float(d.groupby("symbol")["net_abn"].sum().max() / total) if total > 0 else float("nan")
    sessions = d["entry"].nunique()
    if phase == "dev":
        if n < MIN_DEV_OBS:
            verdict = "INSUFFICIENT_DATA"
        else:
            ok = (sessions >= MIN_DEV_SESSIONS and mean_abn > 0 and mean_raw > 0
                  and lower > 0 and share <= MAX_SYMBOL_SHARE)
            verdict = "PASS" if ok else "FAIL"
    else:
        ok = n >= MIN_HOLDOUT_OBS and mean_abn > 0 and mean_raw > 0 and lower > 0
        verdict = "PASS" if ok else "FAIL"
    return {"n": n, "sessions": sessions, "symbols": d["symbol"].nunique(),
            "mean_net_abn_pct": mean_abn * 100, "mean_net_raw_pct": mean_raw * 100,
            "mean_net_abn_index_pct": float(d["net_abn_index"].mean()) * 100,
            "lower_bound_pct": lower * 100, "confidence": confidence,
            "max_symbol_share": share, "win_rate_net_raw": float((d["net_raw"] > 0).mean()),
            "big_moves": int(d["big_move"].sum()),
            "an_dt_fallback": int((d["ts_source"] == "an_dt").sum()), "verdict": verdict}


def evaluate(obs: pd.DataFrame, phase: str, horizons=None) -> pd.DataFrame:
    """Primary rows carry verdicts; secondary thresholds are reported as INFO."""
    horizons = list(horizons or HORIZONS)
    confidence = 1.0 - 0.05 / K_TESTS if phase == "dev" else 0.95
    d0 = obs[obs["period"] == phase]
    out = []
    for hz in horizons:
        dh = d0[d0["horizon"] == hz]
        out.append({"threshold": f">={PRIMARY:.0%}", "role": "PRIMARY", "horizon": hz,
                    **summarise(dh[dh["materiality"] >= PRIMARY], phase, confidence)})
        for name, sub in [(f">={t:.0%}", dh[dh["materiality"] >= t]) for t in SECONDARY] \
                + [("all sizes", dh)]:
            row = summarise(sub, phase, confidence)
            row["verdict"] = "INFO"
            out.append({"threshold": name, "role": "secondary", "horizon": hz, **row})
    return pd.DataFrame(out)

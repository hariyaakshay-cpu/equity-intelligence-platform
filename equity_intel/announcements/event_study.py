"""Announcement event study v1.

Implements docs/architecture/announcement_event_study_preregistration.md
exactly. Pure functions: no network, no database, no orders.
"""
from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

PRE_OPEN_CUTOFF = time(9, 0)
HORIZONS = {"H0": 0, "H1": 1, "H5": 5}
COSTS_PCT = {"H0": 0.1824, "H1": 0.35, "H5": 0.35}
LIQ_MIN_VALUE = 1e8            # INR 10 crore
LIQ_WINDOW, LIQ_MIN_ROWS = 20, 15
DEV = (date(2021, 1, 1), date(2024, 12, 31))
HOLDOUT = (date(2025, 1, 1), date(2026, 10, 31))
MIN_DEV_OBS, MIN_DEV_SESSIONS, MIN_HOLDOUT_OBS = 300, 60, 100
MAX_SYMBOL_SHARE = 0.10
N_BOOT, SEED = 10_000, 20261108
BIG_MOVE = 0.20
INDEX_SYMBOL = "NIFTY500_INDEX"
TS_FMT = "%d-%b-%Y %H:%M:%S"
ANN_COLUMNS = ["symbol", "category", "an_dt", "exchdisstime", "event_ts",
               "ts_source", "attachment", "text", "raw_file"]
OBS_COLUMNS = ["symbol", "category", "entry", "exit", "horizon", "raw", "abn",
               "net_raw", "net_abn", "ts_source", "big_move", "period"]


def parse_ts(value) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "-", "None", "null"):
        return None
    try:
        return datetime.strptime(text, TS_FMT)
    except ValueError:
        return None


def _records(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    return []


def load_announcements(raw_dir: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(Path(raw_dir).glob("NSE_ALL_*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        for r in _records(payload):
            if not isinstance(r, dict):
                continue
            sym = str(r.get("symbol") or "").strip()
            an, dis = parse_ts(r.get("an_dt")), parse_ts(r.get("exchdisstime"))
            if not sym or (an is None and dis is None):
                continue
            rows.append({"symbol": sym,
                         "category": str(r.get("desc") or "").strip(),
                         "an_dt": an, "exchdisstime": dis,
                         "event_ts": dis or an,
                         "ts_source": "exchdisstime" if dis else "an_dt",
                         "attachment": r.get("attchmntFile"),
                         "text": r.get("attchmntText"),
                         "raw_file": f.name})
    df = pd.DataFrame(rows, columns=ANN_COLUMNS)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["symbol", "category", "an_dt", "attachment"])
    return df.reset_index(drop=True)


def load_prices(price_dirs: list[Path], symbol: str) -> pd.DataFrame | None:
    """Daily OHLCV indexed by date; later directories win on overlap."""
    parts = [pd.read_csv(Path(d) / f"{symbol}.csv")
             for d in price_dirs if (Path(d) / f"{symbol}.csv").exists()]
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    return df.set_index("date")[["o", "h", "l", "c", "v"]].astype(float)


def entry_session(event_ts: datetime, sessions: list[date]) -> date | None:
    """First session S with event_ts before 09:00 on S."""
    d = event_ts.date()
    i = (bisect_left(sessions, d) if event_ts.time() < PRE_OPEN_CUTOFF
         else bisect_right(sessions, d))
    return sessions[i] if i < len(sessions) else None


def period_of(d: date) -> str:
    if DEV[0] <= d <= DEV[1]:
        return "dev"
    if HOLDOUT[0] <= d <= HOLDOUT[1]:
        return "holdout"
    return "other"


def _liquid(px: pd.DataFrame, prior: list[date]) -> bool:
    rows = px.reindex(prior).dropna(subset=["c", "v"])
    if len(rows) < LIQ_MIN_ROWS:
        return False
    return float((rows["c"] * rows["v"]).median()) >= LIQ_MIN_VALUE


def build_observations(ann: pd.DataFrame, prices: dict, index: pd.DataFrame,
                       sessions: list[date]) -> tuple[pd.DataFrame, Counter]:
    drops: Counter = Counter()
    pos = {s: i for i, s in enumerate(sessions)}
    units = {}
    for r in ann.itertuples(index=False):
        entry = entry_session(r.event_ts, sessions)
        if entry is None:
            drops["no_entry_session"] += 1
            continue
        key = (r.symbol, entry, r.category)
        if key not in units or (units[key] == "an_dt" and r.ts_source != "an_dt"):
            units[key] = r.ts_source
    rows = []
    for (sym, entry, cat), ts_source in units.items():
        px = prices.get(sym)
        if px is None:
            drops["no_price_file"] += 1
            continue
        i = pos[entry]
        if not _liquid(px, sessions[max(0, i - LIQ_WINDOW):i]):
            drops["illiquid"] += 1
            continue
        if entry not in px.index or entry not in index.index:
            drops["missing_entry_row"] += 1
            continue
        e = px.loc[entry]
        if e["o"] == e["h"] == e["c"]:
            drops["locked_entry"] += 1
            continue
        for hz, k in HORIZONS.items():
            if i + k >= len(sessions):
                drops[f"{hz}:no_exit_session"] += 1
                continue
            ex = sessions[i + k]
            if ex not in px.index or ex not in index.index:
                drops[f"{hz}:missing_exit_row"] += 1
                continue
            raw = px.loc[ex, "c"] / e["o"] - 1.0
            bench = index.loc[ex, "c"] / index.loc[entry, "o"] - 1.0
            cost = COSTS_PCT[hz] / 100.0
            rows.append({"symbol": sym, "category": cat, "entry": entry,
                         "exit": ex, "horizon": hz, "raw": raw,
                         "abn": raw - bench, "net_raw": raw - cost,
                         "net_abn": raw - bench - cost, "ts_source": ts_source,
                         "big_move": abs(raw) > BIG_MOVE,
                         "period": period_of(entry)})
    return pd.DataFrame(rows, columns=OBS_COLUMNS), drops


def bootstrap_lower(values, sessions_of, confidence: float,
                    n_boot: int = N_BOOT, seed: int = SEED) -> float:
    """One-sided lower bound of the mean, resampling whole entry sessions."""
    g = (pd.DataFrame({"s": list(sessions_of), "v": list(values)})
         .groupby("s")["v"].agg(["sum", "count"]))
    sums, counts, m = g["sum"].to_numpy(), g["count"].to_numpy(), len(g)
    if m == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    means = []
    for start in range(0, n_boot, 1000):
        idx = rng.integers(0, m, size=(min(1000, n_boot - start), m))
        means.append(sums[idx].sum(axis=1) / counts[idx].sum(axis=1))
    return float(np.quantile(np.concatenate(means), 1.0 - confidence))


def max_symbol_share(df: pd.DataFrame) -> float:
    total = df["net_abn"].sum()
    if total <= 0:
        return float("nan")
    return float(df.groupby("symbol")["net_abn"].sum().max() / total)


def eligible_categories(obs: pd.DataFrame) -> list[str]:
    dev_h0 = obs[(obs["period"] == "dev") & (obs["horizon"] == "H0")]
    counts = dev_h0.groupby("category").size()
    return sorted(counts[counts >= MIN_DEV_OBS].index)


def evaluate(obs: pd.DataFrame, pairs: list[tuple[str, str]], phase: str,
             k_tests: int) -> pd.DataFrame:
    confidence = 1.0 - 0.05 / k_tests if phase == "dev" else 0.95
    out = []
    for cat, hz in pairs:
        d = obs[(obs["period"] == phase) & (obs["category"] == cat)
                & (obs["horizon"] == hz)]
        n, n_sess = len(d), d["entry"].nunique()
        mean_abn = float(d["net_abn"].mean()) if n else float("nan")
        mean_raw = float(d["net_raw"].mean()) if n else float("nan")
        lower = bootstrap_lower(d["net_abn"], d["entry"], confidence) if n else float("nan")
        share = max_symbol_share(d) if n else float("nan")
        if phase == "dev":
            ok = (n >= MIN_DEV_OBS and n_sess >= MIN_DEV_SESSIONS
                  and mean_abn > 0 and mean_raw > 0 and lower > 0
                  and share <= MAX_SYMBOL_SHARE)
        else:
            ok = n >= MIN_HOLDOUT_OBS and mean_abn > 0 and mean_raw > 0 and lower > 0
        out.append({"category": cat, "horizon": hz, "phase": phase, "n": n,
                    "sessions": n_sess, "mean_net_abn_pct": mean_abn * 100,
                    "mean_net_raw_pct": mean_raw * 100,
                    "lower_bound_pct": lower * 100, "confidence": confidence,
                    "max_symbol_share": share,
                    "win_rate_net_raw": float((d["net_raw"] > 0).mean()) if n else float("nan"),
                    "big_moves": int(d["big_move"].sum()),
                    "an_dt_fallback": int((d["ts_source"] == "an_dt").sum()),
                    "verdict": "PASS" if ok else "FAIL"})
    return pd.DataFrame(out)

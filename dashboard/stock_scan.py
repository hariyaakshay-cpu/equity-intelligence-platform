"""Simple stock scan for the home page (read-only, descriptive).

Reads data/daily_live/<SYMBOL>.csv (date,o,h,l,c,v), the daily prices that
start_equity_dashboard.ps1 refreshes, and lists the latest session's top
gainers, top losers, volume surges and stocks near their 52-week high.
These are numbers only: no buy/sell call, no rank of what to trade.
"""
from __future__ import annotations

import csv
from pathlib import Path
from statistics import median
from typing import Optional

MIN_TRADED_VALUE_CR = 10.0   # 20-day median of close x volume, in Rs crore
TOP = 10
SKIP = {"NIFTY500_INDEX"}
_cache: dict = {}


def _read(path: Path):
    rows = []
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["date"], float(r["h"]), float(r["c"]), float(r["v"])))
            except (KeyError, ValueError):
                continue
    return rows


def _rsi(closes, n=14) -> Optional[float]:
    if len(closes) <= n:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[:n], closes[1:n + 1]):
        d = b - a
        gains += max(d, 0.0); losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    for a, b in zip(closes[n:-1], closes[n + 1:]):
        d = b - a
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def _metrics(symbol, rows):
    if len(rows) < 22:
        return None
    dates = [r[0] for r in rows]; highs = [r[1] for r in rows]
    closes = [r[2] for r in rows]; vols = [r[3] for r in rows]
    prev20 = vols[-21:-1]
    avg_vol = sum(prev20) / len(prev20)
    traded_cr = median(c * v for c, v in zip(closes[-20:], vols[-20:])) / 1e7
    high_52w = max(highs[-252:])
    return {
        "symbol": symbol,
        "date": dates[-1],
        "close": closes[-1],
        "change_pct": (closes[-1] / closes[-2] - 1.0) * 100.0 if closes[-2] else None,
        "rvol": vols[-1] / avg_vol if avg_vol > 0 else None,
        "rsi": _rsi(closes),
        "from_high_pct": (closes[-1] / high_52w - 1.0) * 100.0 if high_52w else None,
        "traded_cr": traded_cr,
    }


def build(daily_dir) -> dict:
    daily_dir = Path(daily_dir)
    files = sorted(p for p in daily_dir.glob("*.csv") if p.stem not in SKIP) if daily_dir.is_dir() else []
    if not files:
        return {"available": False, "message": "No daily prices yet. Run start_equity_dashboard.ps1 (it refreshes them)."}
    stamp = (str(daily_dir), len(files), max(p.stat().st_mtime_ns for p in files))
    if _cache.get("stamp") == stamp:
        return _cache["body"]

    rows = [m for p in files if (m := _metrics(p.stem, _read(p)))]
    asof = max((m["date"] for m in rows), default=None)
    current = [m for m in rows if m["date"] == asof]
    liquid = [m for m in current if m["traded_cr"] >= MIN_TRADED_VALUE_CR]

    def top(key, reverse=True, keep=lambda m: True):
        pool = [m for m in liquid if m[key] is not None and keep(m)]
        return sorted(pool, key=lambda m: (m[key], m["symbol"]) if not reverse else (-m[key], m["symbol"]))[:TOP]

    body = {
        "available": bool(liquid),
        "message": "" if liquid else "No liquid stocks with data for the latest session.",
        "asof": asof,
        "scanned": len(current),
        "liquid": len(liquid),
        "min_traded_cr": MIN_TRADED_VALUE_CR,
        "gainers": top("change_pct", True, lambda m: m["change_pct"] > 0),
        "losers": top("change_pct", False, lambda m: m["change_pct"] < 0),
        "volume": top("rvol", True, lambda m: m["rvol"] >= 1.5),
        "near_high": top("from_high_pct", True, lambda m: m["from_high_pct"] >= -2.0),
    }
    _cache.update(stamp=stamp, body=body)
    return body

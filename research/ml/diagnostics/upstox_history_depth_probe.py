"""Read-only probe: how far back does Upstox daily history go?

Fetches daily candles for a small sample in decade-sized windows (the
documented maximum per request) and reports the earliest and latest date,
session count and the largest calendar gap per instrument. It opens no
database and writes nothing; output goes to stdout as JSON.

Run from the repository root (Settings reads .env from there):
    python research/ml/diagnostics/upstox_history_depth_probe.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, UTC
from pathlib import Path

ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Settings
from core.providers import UpstoxProvider

SAMPLE = {
    "RELIANCE": ("NSE_EQ|INE002A01018", "large cap, long-listed constituent"),
    "VOLTAS": ("NSE_EQ|INE226A01021", "mid cap"),
    "SWIGGY": ("NSE_EQ|INE00H001014", "recent listing (Nov 2024)"),
    "VEDL": ("NSE_EQ|INE205A01025", "E4-flagged break 2026-04-30 (ratio 0.351)"),
    "TMPV": ("NSE_EQ|INE155A01022", "former Tata Motors ISIN, demerged 2025"),
    "NIFTY500": ("NSE_INDEX|Nifty 500", "benchmark index"),
}
END = date(2026, 10, 1)
FLOOR = date(1996, 1, 1)


def windows():
    to = END
    while to > FLOOR:
        frm = max(FLOOR, date(to.year - 10, to.month, to.day) + timedelta(days=1))
        yield frm, to
        to = frm - timedelta(days=1)


def as_dt(d):
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def probe(provider, key):
    bars, requests_made, errors = {}, [], []
    for frm, to in windows():
        try:
            candles = provider.get_historical_data(key, "1day", as_dt(frm), as_dt(to))
        except Exception as exc:  # recorded, not hidden
            errors.append({"window": [str(frm), str(to)], "error": f"{type(exc).__name__}: {exc}"})
            break
        got = {c.timestamp.date(): c.close for c in candles if c.timestamp is not None}
        requests_made.append({"window": [str(frm), str(to)], "candles": len(candles)})
        bars.update(got)
        if not got:
            break  # nothing in this decade: earlier decades are not tried
    ordered = sorted(bars)
    jumps = [
        {"date": str(b), "close_ratio": round(bars[b] / bars[a], 4)}
        for a, b in zip(ordered, ordered[1:])
        if bars[a] and bars[b] and not 0.5 <= bars[b] / bars[a] <= 2.0
    ]
    gaps = [(b - a).days for a, b in zip(ordered, ordered[1:])]
    big = max(range(len(gaps)), key=gaps.__getitem__) if gaps else None
    return {
        "earliest": str(ordered[0]) if ordered else None,
        "latest": str(ordered[-1]) if ordered else None,
        "sessions": len(ordered),
        "largest_gap_days": gaps[big] if gaps else None,
        "largest_gap_between": [str(ordered[big]), str(ordered[big + 1])] if gaps else None,
        "weekend_dated_bars": [str(d) for d in ordered if d.weekday() >= 5],
        "close_jumps_outside_0.5_2": jumps,
        "requests": requests_made,
        "errors": errors,
    }


def over_limit(provider, key):
    """One request spanning more than a decade, to record the API's response."""
    try:
        candles = provider.get_historical_data(key, "1day", as_dt(date(2010, 1, 1)), as_dt(END))
        return f"accepted: {len(candles)} candles for 2010-01-01..{END}"
    except Exception as exc:
        return f"refused: {type(exc).__name__}: {exc}"


def main():
    provider = UpstoxProvider(Settings())
    out = {"probe_run_at": datetime.now(UTC).isoformat(), "end_date": str(END), "results": {}}
    for name, (key, why) in SAMPLE.items():
        out["results"][name] = {"instrument_key": key, "why": why, **probe(provider, key)}
    out["over_decade_request_RELIANCE"] = over_limit(provider, SAMPLE["RELIANCE"][0])
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

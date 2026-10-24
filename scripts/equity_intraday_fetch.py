"""Download 5-minute candles for the universe into data/intraday_cache/<SYMBOL>.csv (read-only on Upstox).
Run on your PC with your Upstox token, AFTER equity_intraday_probe.py shows the window limit.
Resumable: symbols with an existing cache file are skipped unless --refresh.

    python scripts/equity_intraday_fetch.py --days 400 --chunk-days 28
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Settings
from core.providers.upstox_provider import UpstoxProvider
from equity_intel.intraday.probe import IST

PAUSE = 0.7


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", default=str(ROOT / "research" / "intraday" / "universe.csv"))
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--chunk-days", type=int, default=28)
    ap.add_argument("--limit", type=int, default=0, help="only first N symbols (smoke test)")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args(argv)
    with open(a.universe, newline="") as f:
        uni = list(csv.DictReader(f))
    if a.limit:
        uni = uni[:a.limit]
    cache = ROOT / "data" / "intraday_cache"
    cache.mkdir(parents=True, exist_ok=True)
    provider = UpstoxProvider(Settings())
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=a.days)
    for n, row in enumerate(uni, 1):
        path = cache / f"{row['symbol']}.csv"
        if path.exists() and not a.refresh:
            continue
        seen, errors = {}, 0
        lo = start
        while lo < end:
            hi = min(lo + timedelta(days=a.chunk_days), end)
            try:
                for c in provider.get_historical_data(row["instrument_key"], "5minute", lo, hi):
                    if c.timestamp is not None:
                        seen[c.timestamp.astimezone(IST).isoformat()] = c
            except Exception as exc:
                errors += 1
                print(f"  {row['symbol']} {lo.date()}..{hi.date()}: {type(exc).__name__}: {str(exc)[:120]}")
            lo = hi
            time.sleep(PAUSE)
        with path.open("w", newline="") as f:
            w = csv.writer(f); w.writerow(["ts", "o", "h", "l", "c", "v"])
            for ts in sorted(seen):
                c = seen[ts]; w.writerow([ts, c.open, c.high, c.low, c.close, c.volume])
        print(f"[{n}/{len(uni)}] {row['symbol']}: {len(seen)} bars, {errors} chunk errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

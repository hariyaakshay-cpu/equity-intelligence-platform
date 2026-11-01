"""Download daily candles for the equity universe into data/daily_history/<SYMBOL>.csv (read-only on Upstox).
Writes only CSV files; it does NOT touch data/equity_intel.db (the symbol list is read from it read-only).
Run on your PC with a fresh Upstox token (python scripts/upstox_auth.py first). Resumable: existing files are skipped unless --refresh.

    python scripts/equity_daily_history_fetch.py --start 2021-10-01
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Settings
from core.providers.upstox_provider import UpstoxProvider
from equity_intel.config import session_date

PAUSE = 0.7
INDEX_KEY = "NSE_INDEX|Nifty 500"


def _symbols(db: Path):
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT DISTINCT symbol, instrument_key FROM acquired_observations "
                            "WHERE instrument_key IS NOT NULL ORDER BY symbol").fetchall()
    finally:
        conn.close()
    return [(s, k) for s, k in rows] + [("NIFTY500_INDEX", INDEX_KEY)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2021, 10, 1))
    ap.add_argument("--chunk-days", type=int, default=180)
    ap.add_argument("--limit", type=int, default=0, help="only first N symbols (smoke test)")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args(argv)
    symbols = _symbols(ROOT / "data" / "equity_intel.db")
    if a.limit:
        symbols = symbols[:a.limit]
    out_dir = ROOT / "data" / "daily_history"
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = UpstoxProvider(Settings())
    end = datetime.now(timezone.utc)
    start = datetime.combine(a.start, dtime.min, tzinfo=timezone.utc)
    for n, (sym, key) in enumerate(symbols, 1):
        path = out_dir / f"{sym}.csv"
        if path.exists() and not a.refresh:
            continue
        seen, errors, lo = {}, 0, start
        while lo < end:
            hi = min(lo + timedelta(days=a.chunk_days), end)
            try:
                for c in provider.get_historical_data(key, "1day", lo, hi):
                    d = session_date(c.timestamp)
                    if d is not None:
                        seen[d.isoformat()] = c
            except Exception as exc:
                errors += 1
                print(f"  {sym} {lo.date()}..{hi.date()}: {type(exc).__name__}: {str(exc)[:120]}")
            lo = hi
            time.sleep(PAUSE)
        if errors:
            print(f"[{n}/{len(symbols)}] {sym}: NOT saved ({errors} chunk errors); rerun to retry")
            continue
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "o", "h", "l", "c", "v"])
            for d in sorted(seen):
                c = seen[d]
                w.writerow([d, c.open, c.high, c.low, c.close, c.volume])
        print(f"[{n}/{len(symbols)}] {sym}: {len(seen)} sessions, {errors} chunk errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

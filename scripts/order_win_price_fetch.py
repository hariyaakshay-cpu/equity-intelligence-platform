"""Order-win study v2: daily candles for order-win symbols missing from the
NIFTY 500 price files, into data/daily_history_orders/<SYMBOL>.csv.

Run on your PC after the Upstox login (python scripts/upstox_auth.py):

    python scripts/order_win_price_fetch.py --limit 2   # dry run
    python scripts/order_win_price_fetch.py

Reads research/announcements/order_wins/symbols.csv. Instrument keys come from
the newest data/reference/upstox_NSE_instruments_*.json.gz. Skips symbols that
already have a file in data/daily_history/ or data/daily_history_orders/.
Read-only on Upstox; writes CSV files only. Resumable.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from core.providers.upstox_provider import UpstoxProvider  # noqa: E402
from equity_intel.config import session_date  # noqa: E402

PAUSE = 0.7
EQ_TYPES = {"EQ", "BE", "SM", "ST", "BZ"}


def instrument_keys() -> dict[str, str]:
    newest = sorted((ROOT / "data" / "reference").glob("upstox_NSE_instruments_*.json.gz"))[-1]
    rows = json.load(gzip.open(newest))
    return {r["trading_symbol"]: r["instrument_key"] for r in rows
            if r.get("segment") == "NSE_EQ" and r.get("instrument_type") in EQ_TYPES}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=date.fromisoformat, default=date(2013, 9, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 11, 6))
    ap.add_argument("--chunk-days", type=int, default=180)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    out_dir = ROOT / "data" / "daily_history_orders"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(ROOT / "research" / "announcements" / "order_wins" / "symbols.csv",
              encoding="utf-8") as f:
        symbols = [r["symbol"] for r in csv.DictReader(f)]
    have = {p.stem for p in (ROOT / "data" / "daily_history").glob("*.csv")}
    have |= {p.stem for p in out_dir.glob("*.csv")}
    keys = instrument_keys()
    todo = [s for s in symbols if s not in have]
    no_key = [s for s in todo if s not in keys]
    todo = [s for s in todo if s in keys]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo)} to fetch; {len(no_key)} without an Upstox key: {no_key}")
    provider = UpstoxProvider(Settings())
    start = datetime.combine(a.start, dtime.min, tzinfo=timezone.utc)
    end = datetime.combine(a.end, dtime.max, tzinfo=timezone.utc)
    for n, sym in enumerate(todo, 1):
        seen, errors, lo = {}, 0, start
        while lo < end:
            hi = min(lo + timedelta(days=a.chunk_days), end)
            try:
                for c in provider.get_historical_data(keys[sym], "1day", lo, hi):
                    d = session_date(c.timestamp)
                    if d is not None:
                        seen[d.isoformat()] = c
            except Exception as exc:
                errors += 1
                print(f"  {sym} {lo.date()}..{hi.date()}: {type(exc).__name__}: {str(exc)[:120]}")
            lo = hi
            time.sleep(PAUSE)
        if errors:
            print(f"[{n}/{len(todo)}] {sym}: NOT saved ({errors} chunk errors); rerun to retry")
            continue
        with (out_dir / f"{sym}.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "o", "h", "l", "c", "v"])
            for d in sorted(seen):
                c = seen[d]
                w.writerow([d, c.open, c.high, c.low, c.close, c.volume])
        print(f"[{n}/{len(todo)}] {sym}: {len(seen)} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

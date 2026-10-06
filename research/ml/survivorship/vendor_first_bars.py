"""Record first and last Upstox daily bar dates for Nifty 500 names (spec 5A.2 items 1 and 4).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Read-only: opens the equity_intel database read-only, calls the Upstox historical
candle endpoint, writes only sources/vendor_first_bars.json (symbol, instrument key,
first bar date, last bar date, bar count, and the sha256 of the bar-date list).
No bars are stored.

--removed instead takes the symbols that left the Nifty 500 in the reconstructed period
(nifty500_events.csv, not in the snapshot), resolves each by trading symbol in the newest
local Upstox instrument master, and writes sources/vendor_removed_names.json. Names the
master cannot resolve are listed as UNRESOLVED; resolution is by symbol only, so a reused
symbol would be a false match (ISIN is not verified).

Run from the repository root that holds .env and data/ (Settings reads .env there):
    python <path>/research/ml/survivorship/vendor_first_bars.py [--db data/equity_intel.db]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sources" / "vendor_first_bars.json"
OUT_REMOVED = HERE / "sources" / "vendor_removed_names.json"
FROM_YEAR, TO_DATE, STEP = 2000, date(2026, 10, 2), 5  # the API refuses windows over ten years


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/equity_intel.db")
    ap.add_argument("--removed", action="store_true")
    ap.add_argument("--since", default="2020-03-27", help="with --removed: earliest effective date")
    args = ap.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    from config import Settings
    from core.providers import UpstoxProvider

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    run = con.execute("select run_id from acquisition_runs where status='COMPLETE' "
                      "order by run_started_at desc limit 1").fetchone()[0]
    keys = dict(con.execute("select symbol, instrument_key from instrument_mappings "
                            "where run_id=? and instrument_key is not null", (run,)).fetchall())
    unresolved: list[str] = []
    out = OUT
    if args.removed:
        import csv
        import glob
        import gzip
        master = sorted(glob.glob("data/reference/upstox_NSE_instruments_*.json.gz"))[-1]
        eq = {r["trading_symbol"]: r["instrument_key"] for r in json.load(gzip.open(master))
              if r.get("segment") == "NSE_EQ" and r.get("instrument_type") == "EQ"}
        snap = {r["Symbol"] for r in csv.DictReader(open("data/reference/nifty500_constituents_2026-09-24.csv", encoding="utf-8"))}
        events = csv.DictReader((HERE / "nifty500_events.csv").open(encoding="utf-8"))
        left = {r["symbol"] for r in events if r["action"] == "EXCLUDE" and r["effective_date"] >= args.since} - snap
        keys = {s: eq[s] for s in left if s in eq}
        unresolved = sorted(left - set(keys))
        out = OUT_REMOVED
    provider = UpstoxProvider(Settings())
    result = {"acquisition_run_id": run, "unresolved": unresolved, "instrument_master": master if args.removed else None, "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
              "symbols": {}}
    if out.exists():  # resume: keep symbols already fetched without error, redo the rest
        prior = json.loads(out.read_text(encoding="utf-8"))["symbols"]
        result["symbols"] = {k: v for k, v in prior.items() if not v["error"] and k in keys}
    for n, (symbol, key) in enumerate(sorted(keys.items()), 1):
        if symbol in result["symbols"]:
            continue
        dates: set[str] = set()
        failed: list[str] = []
        for y in range(FROM_YEAR, TO_DATE.year + 1, STEP):
            end = min(date(y + STEP, 1, 1), TO_DATE)
            candles = None
            for attempt in range(4):  # the endpoint rate-limits (HTTP 429): wait, then retry
                try:
                    candles = provider.get_historical_data(key, "1day", datetime(y, 1, 1, tzinfo=UTC),
                                                           datetime(end.year, end.month, end.day, tzinfo=UTC))
                    break
                except Exception as e:  # recorded, never patched
                    last = f"{type(e).__name__}: {e}"[:120]
                    time.sleep(20 * (attempt + 1))
            if candles is None:
                failed.append(f"{y}-{end.year}: {last}")
                continue
            time.sleep(0.3)
            dates |= {c.timestamp.date().isoformat() for c in candles if c.timestamp}
        ds = sorted(dates)
        result["symbols"][symbol] = {
            "instrument_key": key, "first_bar": ds[0] if ds else None, "last_bar": ds[-1] if ds else None,
            "bars": len(ds), "dates_sha256": hashlib.sha256("\n".join(ds).encode()).hexdigest(), "error": "; ".join(failed) or None}
        if n % 25 == 0:
            print(n, "/", len(keys), flush=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print("symbols", len(result["symbols"]), "errors", sum(1 for v in result["symbols"].values() if v["error"]))


if __name__ == "__main__":
    main()

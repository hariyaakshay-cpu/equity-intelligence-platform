"""Order-win study v2: fetch shares outstanding (NSE issuedSize) per symbol.

    python scripts/order_win_shares_fetch.py            # all symbols in the list
    python scripts/order_win_shares_fetch.py --limit 3  # dry run

Reads research/announcements/order_wins/symbols.csv (column `symbol`).
Saves each raw NSE quote response unchanged plus shares.csv
(symbol, issued_size, http_status, error) in
research/announcements/order_wins/shares_<run_ts>/. Read-only on NSE.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import time
from datetime import datetime
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "research" / "announcements" / "order_wins"
NSE_HOME = "https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE"
NSE_API = "https://www.nseindia.com/api/quote-equity"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                      "Accept-Language": "en-US,en;q=0.9", "Referer": NSE_HOME})
    s.get(NSE_HOME, timeout=20)
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pause", type=float, default=2.0)
    args = ap.parse_args()
    with open(BASE / "symbols.csv", encoding="utf-8") as f:
        symbols = [r["symbol"] for r in csv.DictReader(f)]
    if args.limit:
        symbols = symbols[:args.limit]
    out = BASE / f"shares_{datetime.now():%Y%m%dT%H%M%S}"
    (out / "raw").mkdir(parents=True)
    print(f"{len(symbols)} symbols, ~{len(symbols) * args.pause / 60:.0f} min")
    s, rows = session(), []
    for i, sym in enumerate(symbols, 1):
        row = {"symbol": sym, "issued_size": "", "http_status": "", "sha256": "", "error": ""}
        try:
            if i % 40 == 0:
                s = session()
            resp = s.get(NSE_API, params={"symbol": sym}, timeout=30)
            row["http_status"] = resp.status_code
            (out / "raw" / f"{sym}.json").write_bytes(resp.content)
            row["sha256"] = hashlib.sha256(resp.content).hexdigest()
            row["issued_size"] = resp.json().get("securityInfo", {}).get("issuedSize", "")
        except Exception as exc:  # recorded, never hidden
            row["error"] = f"{type(exc).__name__}: {exc}"[:200]
        rows.append(row)
        print(f"[{i}/{len(symbols)}] {sym}: status={row['http_status']} "
              f"issuedSize={row['issued_size']} {row['error']}")
        time.sleep(args.pause)
    with open(out / "shares.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()

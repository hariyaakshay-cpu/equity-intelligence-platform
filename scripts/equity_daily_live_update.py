"""Incremental update of data/daily_live/<SYMBOL>.csv (date,o,h,l,c,v) - read-only on Upstox.

    python scripts/equity_daily_live_update.py

For every existing file: fetch daily candles from 7 days before its last date up
to today with ONE request (Upstox V3 historical-candle, documented as not needing
authorization), merge (new days added, overlapping days replaced, older history
kept) and write atomically. About 490 requests instead of a full ~1,500-request
re-download, so it finishes in a few minutes and stays under Upstox rate limits.
A stock that fails keeps its old file. Exit code 1 only if the NIFTY 500 index failed.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from equity_intel.config import IST, session_date  # noqa: E402
from equity_intel.paper_board import daily_update as du  # noqa: E402

DAILY = ROOT / "data" / "daily_live"
URL = "https://api.upstox.com/v3/historical-candle/{key}/days/1/{to}/{frm}"
INDEX, INDEX_KEY = "NIFTY500_INDEX", "NSE_INDEX|Nifty 500"
PAUSE = 0.25
EQ_TYPES = {"EQ", "BE", "SM", "ST", "BZ"}


def keys() -> dict:
    newest = sorted((ROOT / "data" / "reference").glob("upstox_NSE_instruments_*.json.gz"))[-1]
    out = {r["trading_symbol"]: r["instrument_key"] for r in json.load(gzip.open(newest))
           if r.get("segment") == "NSE_EQ" and r.get("instrument_type") in EQ_TYPES}
    out[INDEX] = INDEX_KEY
    return out


def read(path: Path) -> dict:
    with path.open(newline="") as f:
        return {r["date"]: (r["o"], r["h"], r["l"], r["c"], r["v"]) for r in csv.DictReader(f)}


def write(path: Path, rows: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "o", "h", "l", "c", "v"])
        for d, r in rows.items():
            w.writerow([d, *r])
    os.replace(tmp, path)


def fetch(session: requests.Session, key: str, frm: date, to: date) -> dict:
    for attempt in range(4):
        resp = session.get(URL.format(key=quote(key, safe=""), to=to.isoformat(), frm=frm.isoformat()), timeout=20)
        if resp.status_code == 429 and attempt < 3:
            time.sleep(2 ** (attempt + 1))
            continue
        resp.raise_for_status()
        out = {}
        for c in resp.json().get("data", {}).get("candles", []):
            d = session_date(datetime.fromisoformat(c[0].replace("Z", "+00:00")))
            if d is not None and (d < to or datetime.now(IST).hour >= 18):    # no partial candle for today
                out[d.isoformat()] = tuple(str(float(x)) for x in c[1:6])          # same text format as the files
        return out
    raise RuntimeError("HTTP 429 after retries")


def main() -> int:
    today = datetime.now(IST).date()
    settings = Settings()
    token = settings.UPSTOX_ANALYTICS_TOKEN or settings.UPSTOX_ACCESS_TOKEN
    s = requests.Session()
    s.headers.update({"Accept": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    k = keys()
    files = sorted(DAILY.glob("*.csv"))
    updated = unchanged = 0
    failed, no_key = [], []
    for n, path in enumerate(files, 1):
        sym = path.stem
        if sym not in k:
            no_key.append(sym)
            continue
        try:
            old = read(path)
            last = date.fromisoformat(max(old)) if old else date(2025, 6, 1)
            new = fetch(s, k[sym], du.fetch_from(last), today)
            merged = du.merge(old, new)
            if merged != old:
                write(path, merged)
                updated += 1
            else:
                unchanged += 1
        except Exception as exc:  # recorded, never hidden; the old file is kept
            failed.append(sym)
            print(f"[{n}/{len(files)}] {sym}: FAILED {type(exc).__name__}: {str(exc)[:120]}")
        time.sleep(PAUSE)
    last_index = max(read(DAILY / f"{INDEX}.csv")) if (DAILY / f"{INDEX}.csv").exists() else None
    print(f"daily_live update {today}: {updated} updated, {unchanged} unchanged, {len(failed)} failed, "
          f"{len(no_key)} without an instrument key; NIFTY500_INDEX now ends {last_index}")
    if no_key:
        print("no instrument key:", ", ".join(no_key[:20]) + (" ..." if len(no_key) > 20 else ""))
    return 1 if INDEX in failed else 0


if __name__ == "__main__":
    sys.exit(main())

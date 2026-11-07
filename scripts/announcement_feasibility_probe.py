"""Announcement data feasibility probe - Step 1a: field discovery.

Read-only. Fetches a small sample of corporate announcements from NSE (and
optionally BSE) and saves each raw response unchanged, so we can see which
fields exist (especially a time-of-day field) and how far back history goes.

Writes ONLY under research/announcements/probe_<run_ts>/.
No categories, no classification, no returns, no database writes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "research" / "announcements"

NSE_HOME = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_API = "https://www.nseindia.com/api/corporate-announcements"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

DEFAULT_SYMBOLS = ["RELIANCE", "TCS", "HDFCBANK", "LT", "BEL"]
DEFAULT_BSE_CODES = {"RELIANCE": "500325", "TCS": "532540"}
# One 14-day window per period, inside results seasons, to find how far back
# history goes and whether old records carry a time-of-day.
DEFAULT_WINDOW_STARTS = ["2012-05-01", "2015-05-01", "2018-05-01",
                         "2021-05-01", "2024-05-01", "2026-10-15"]
WINDOW_DAYS = 14
TIME_HINTS = ("dt", "date", "time")


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Accept": "application/json, text/plain, */*",
                      "Accept-Language": "en-US,en;q=0.9",
                      "Referer": NSE_HOME})
    s.get(NSE_HOME, timeout=20)  # sets the cookies the API expects
    return s


def fetch_nse(s: requests.Session, symbol: str, start: date, end: date):
    params = {"index": "equities", "symbol": symbol,
              "from_date": start.strftime("%d-%m-%Y"),
              "to_date": end.strftime("%d-%m-%Y")}
    return s.get(NSE_API, params=params, timeout=30)


def fetch_bse(s: requests.Session, code: str, start: date, end: date):
    # Page 1 only: enough for field discovery, NOT a coverage count.
    params = {"pageno": 1, "strCat": -1,
              "strPrevDate": start.strftime("%Y%m%d"),
              "strToDate": end.strftime("%Y%m%d"),
              "strScrip": code, "strSearch": "P", "strType": "C",
              "subcategory": -1}
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Referer": "https://www.bseindia.com/",
               "Origin": "https://www.bseindia.com"}
    return s.get(BSE_API, params=params, headers=headers, timeout=30)


def records_of(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "Table"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def note_fields(inventory: dict, source: str, records: list) -> None:
    fields = inventory.setdefault(source, {})
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for key, val in rec.items():
            entry = fields.setdefault(key, {"count": 0, "examples": []})
            entry["count"] += 1
            text = str(val)[:80]
            if text not in entry["examples"] and len(entry["examples"]) < 3:
                entry["examples"].append(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    ap.add_argument("--windows", nargs="+", default=DEFAULT_WINDOW_STARTS,
                    help="window start dates, YYYY-MM-DD")
    ap.add_argument("--no-bse", action="store_true")
    ap.add_argument("--pause", type=float, default=3.0,
                    help="seconds between requests")
    args = ap.parse_args()

    run_ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    out = (OUT_ROOT / f"probe_{run_ts}").resolve()
    if OUT_ROOT.resolve() not in out.parents:
        raise SystemExit(f"refusing to write outside {OUT_ROOT}")
    (out / "raw").mkdir(parents=True)

    jobs = []
    for w in args.windows:
        start = date.fromisoformat(w)
        end = start + timedelta(days=WINDOW_DAYS - 1)
        for sym in args.symbols:
            jobs.append(("NSE", sym, sym, start, end))
            if not args.no_bse and sym in DEFAULT_BSE_CODES:
                jobs.append(("BSE", sym, DEFAULT_BSE_CODES[sym], start, end))

    nse = nse_session()
    bse = requests.Session()
    manifest, inventory = [], {}
    for source, sym, key, start, end in jobs:
        row = {"source": source, "symbol": sym, "window_start": start,
               "window_end": end, "http_status": "", "n_records": 0,
               "raw_file": "", "sha256": "", "error": "",
               "retrieved_ts": datetime.now().isoformat(timespec="seconds")}
        try:
            resp = (fetch_nse(nse, key, start, end) if source == "NSE"
                    else fetch_bse(bse, key, start, end))
            row["http_status"] = resp.status_code
            raw_name = f"{source}_{sym}_{start}.json"
            (out / "raw" / raw_name).write_bytes(resp.content)
            row["raw_file"] = raw_name
            row["sha256"] = hashlib.sha256(resp.content).hexdigest()
            records = records_of(resp.json())
            row["n_records"] = len(records)
            note_fields(inventory, source, records)
        except Exception as exc:  # recorded, never hidden
            row["error"] = f"{type(exc).__name__}: {exc}"[:200]
        manifest.append(row)
        print(f"{source} {sym} {start}: status={row['http_status']} "
              f"n={row['n_records']} {row['error']}")
        time.sleep(args.pause)

    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    (out / "field_inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nWrote {out}")
    for source, fields in inventory.items():
        hits = [k for k in fields if any(h in k.lower() for h in TIME_HINTS)]
        print(f"{source}: {len(fields)} fields; date/time-like: {hits}")


if __name__ == "__main__":
    main()

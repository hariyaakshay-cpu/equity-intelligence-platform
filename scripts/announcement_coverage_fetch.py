"""Announcement feasibility - Step 1b fetch: market-wide coverage sample (NSE).

Read-only. For one fixed day per month (the 15th, moved to the next Monday if
it falls on a weekend), 2012-01 to the latest complete month, requests ALL
NSE equity announcements for that day (no symbol filter) and saves each raw
response unchanged. The sample days are fixed by rule, not chosen by result.

Writes ONLY under research/announcements/coverage_<run_ts>/.
No parsing beyond counting records, no classification, no returns.
Analysis runs separately on the saved raw files.
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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def sample_days(first: date, last: date) -> list[date]:
    days, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        d = date(y, m, 15)
        if d.weekday() >= 5:                     # Sat/Sun -> next Monday
            d += timedelta(days=7 - d.weekday())
        if d <= last:
            days.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return days


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Accept": "application/json, text/plain, */*",
                      "Accept-Language": "en-US,en;q=0.9",
                      "Referer": NSE_HOME})
    s.get(NSE_HOME, timeout=20)  # sets the cookies the API expects
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--first", default="2012-01-01")
    ap.add_argument("--last", default="2026-10-31")
    ap.add_argument("--pause", type=float, default=3.0,
                    help="seconds between requests")
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N days (0 = all); use 3 for a dry run")
    ap.add_argument("--all-days", action="store_true",
                    help="every weekday from --first to --last, not one per month")
    args = ap.parse_args()

    d0, d1 = date.fromisoformat(args.first), date.fromisoformat(args.last)
    if args.all_days:
        days = [d0 + timedelta(n) for n in range((d1 - d0).days + 1)
                if (d0 + timedelta(n)).weekday() < 5]
    else:
        days = sample_days(d0, d1)
    if args.limit:
        days = days[:args.limit]

    run_ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    out = (OUT_ROOT / f"coverage_{run_ts}").resolve()
    if OUT_ROOT.resolve() not in out.parents:
        raise SystemExit(f"refusing to write outside {OUT_ROOT}")
    (out / "raw").mkdir(parents=True)
    print(f"{len(days)} sample days, ~{len(days) * args.pause / 60:.0f} min")

    s = nse_session()
    manifest = []
    for i, d in enumerate(days, 1):
        row = {"day": d, "http_status": "", "n_records": 0, "n_symbols": 0,
               "raw_file": "", "sha256": "", "error": "",
               "retrieved_ts": datetime.now().isoformat(timespec="seconds")}
        try:
            if i % 40 == 0:
                s = nse_session()                # refresh cookies on long runs
            resp = s.get(NSE_API, params={"index": "equities",
                                          "from_date": d.strftime("%d-%m-%Y"),
                                          "to_date": d.strftime("%d-%m-%Y")},
                         timeout=60)
            row["http_status"] = resp.status_code
            raw_name = f"NSE_ALL_{d}.json"
            (out / "raw" / raw_name).write_bytes(resp.content)
            row["raw_file"] = raw_name
            row["sha256"] = hashlib.sha256(resp.content).hexdigest()
            payload = resp.json()
            recs = payload if isinstance(payload, list) else payload.get("data", [])
            row["n_records"] = len(recs)
            row["n_symbols"] = len({r.get("symbol") for r in recs
                                    if isinstance(r, dict)})
        except Exception as exc:  # recorded, never hidden
            row["error"] = f"{type(exc).__name__}: {exc}"[:200]
        manifest.append(row)
        print(f"[{i}/{len(days)}] {d}: status={row['http_status']} "
              f"n={row['n_records']} symbols={row['n_symbols']} {row['error']}")
        time.sleep(args.pause)

    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()

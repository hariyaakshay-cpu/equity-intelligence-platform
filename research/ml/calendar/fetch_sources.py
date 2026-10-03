"""Fetch the source snapshots for the verified NSE trading calendar (spec 5A.1).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Read-only. Writes only under research/ml/calendar/sources/:

- nse_holiday_master/trading_<year>.json — NSE holiday-master API, per year
  (primary source for exchange holidays).
- nse_circulars/session_circulars.json — NSE circular index entries whose
  subject mentions a holiday or a trading session (primary source for special
  sessions), all departments, month by month. Mock-trading circulars are kept
  in the index but marked, since mock sessions are not market sessions.
- nse_circulars/pdf/<number>.pdf — the circulars cited in resolutions.csv
  (the evidence for each special session or exception).
- vendor_bars/<name>.json — Upstox daily bar dates for two indices and one
  long-listed equity (cross-check only).
- fetch_log.json — what was requested, when, and the sha256 of every file.

Run from the repository root (Settings reads .env there):
    python research/ml/calendar/fetch_sources.py [--skip-vendor] [--skip-nse]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, UTC
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIRST_YEAR, LAST_YEAR = 2011, 2026
SPAN_END = date(2026, 10, 2)
NSE = "https://www.nseindia.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")
SESSION_SUBJECT = re.compile(
    r"holiday|muhurat|special live|live trading|trading session|budget|"
    r"market timings|closure|closed|disaster recovery|\bDR\b",
    re.I,
)
VENDOR = {
    "nifty500": "NSE_INDEX|Nifty 500",
    "nifty50": "NSE_INDEX|Nifty 50",
    "reliance": "NSE_EQ|INE002A01018",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": NSE + "/", "Accept": "application/json"})
    try:
        s.get(NSE + "/", timeout=20)  # cookies, if offered; the API answers without them too
    except requests.RequestException:
        pass
    return s


def get_json(s: requests.Session, url: str):
    for attempt in range(4):
        r = s.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
        time.sleep(2 + 2 * attempt)
    raise RuntimeError(f"HTTP {r.status_code} for {url}")


def fetch_holiday_master(s, log):
    out = SOURCES / "nse_holiday_master"
    out.mkdir(parents=True, exist_ok=True)
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        url = f"{NSE}/api/holiday-master?type=trading&year={year}"
        data = get_json(s, url)
        path = out / f"trading_{year}.json"
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        log.append({"url": url, "file": path.relative_to(HERE).as_posix(), "sha256": sha256(path)})
        time.sleep(1)


def fetch_circulars(s, log):
    out = SOURCES / "nse_circulars"
    out.mkdir(parents=True, exist_ok=True)
    kept, scanned = [], 0
    month = date(FIRST_YEAR, 1, 1)
    while month <= SPAN_END:
        nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = min(nxt - timedelta(days=1), SPAN_END)
        url = (f"{NSE}/api/circulars?fromDate={month:%d-%m-%Y}"
               f"&toDate={last:%d-%m-%Y}")
        rows = get_json(s, url).get("data", [])
        scanned += len(rows)
        log.append({"url": url, "rows": len(rows)})
        for row in rows:
            subject = row.get("sub") or ""
            if SESSION_SUBJECT.search(subject):
                kept.append({
                    "date": row.get("cirDate"),
                    "number": row.get("circDisplayNo"),
                    "department": row.get("circDepartment"),
                    "subject": subject.strip(),
                    "link": row.get("circFilelink"),
                    "mock": bool(re.search(r"\bmock\b", subject, re.I)),
                })
        month = nxt
        time.sleep(1)
    unique = {(k["number"], k["subject"]): k for k in kept}
    rows = sorted(unique.values(), key=lambda k: (k["date"] or "", k["number"] or ""))
    path = out / "session_circulars.json"
    path.write_text(json.dumps({
        "filter": SESSION_SUBJECT.pattern,
        "circulars_scanned": scanned,
        "rows": rows,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    log.append({"file": path.relative_to(HERE).as_posix(), "sha256": sha256(path), "kept": len(rows)})


def fetch_cited_pdfs(s, log):
    import csv

    out = SOURCES / "nse_circulars" / "pdf"
    out.mkdir(parents=True, exist_ok=True)
    with open(HERE / "resolutions.csv", newline="", encoding="utf-8") as fh:
        numbers = {n.strip() for row in csv.DictReader(fh) for n in row["circulars"].split(";")}
    for number in sorted(numbers):
        dept, num = number.split("/")[1:3]
        name = f"{dept.upper()}{num}.pdf"
        url = f"https://nsearchives.nseindia.com/content/circulars/{name}"
        r = s.get(url, timeout=30)
        r.raise_for_status()
        path = out / name
        path.write_bytes(r.content)
        log.append({"url": url, "file": path.relative_to(HERE).as_posix(), "sha256": sha256(path)})
        time.sleep(0.5)


def fetch_vendor(log):
    from config import Settings
    from core.providers import UpstoxProvider

    provider = UpstoxProvider(Settings())
    out = SOURCES / "vendor_bars"
    out.mkdir(parents=True, exist_ok=True)
    for name, key in VENDOR.items():
        dates = set()
        start = date(FIRST_YEAR, 1, 1)
        while start <= SPAN_END:  # under-a-decade windows (the API refuses longer)
            end = min(date(start.year + 5, 1, 1) - timedelta(days=1), SPAN_END)
            candles = provider.get_historical_data(
                key, "1day",
                datetime(start.year, start.month, start.day, tzinfo=UTC),
                datetime(end.year, end.month, end.day, tzinfo=UTC))
            dates |= {c.timestamp.date().isoformat() for c in candles if c.timestamp}
            start = end + timedelta(days=1)
        path = out / f"{name}.json"
        path.write_text(json.dumps({"instrument_key": key, "dates": sorted(dates)}, indent=0),
                        encoding="utf-8")
        log.append({"vendor": key, "file": path.relative_to(HERE).as_posix(),
                    "sha256": sha256(path), "bars": len(dates)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-nse", action="store_true")
    ap.add_argument("--skip-vendor", action="store_true")
    args = ap.parse_args()
    log = []
    if not args.skip_nse:
        s = nse_session()
        fetch_holiday_master(s, log)
        fetch_circulars(s, log)
        fetch_cited_pdfs(s, log)
    if not args.skip_vendor:
        fetch_vendor(log)
    path = SOURCES / "fetch_log.json"
    previous = json.loads(path.read_text()) if path.exists() else []
    previous.append({"fetched_at": datetime.now(UTC).isoformat(), "entries": log})
    path.write_text(json.dumps(previous, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

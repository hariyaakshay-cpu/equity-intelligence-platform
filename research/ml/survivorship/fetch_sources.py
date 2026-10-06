"""Fetch the NSE Indices press releases used as Nifty 500 membership evidence (spec 5A.2).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Read-only. Writes only under research/ml/survivorship/sources/:

- press_releases/index.json      every press release listed on niftyindices.com
                                 (date, path, title), as served on the fetch date
- press_releases/pdf/<name>.pdf  the releases whose title announces equity-index
                                 changes, replacements or exclusions, 2011 onwards
                                 (fixed-income, SME, IPO and bond releases are skipped)
- fetch_log.json                 request time, status, size and sha256 of every file

Run from anywhere:  python research/ml/survivorship/fetch_sources.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "sources" / "press_releases"
BASE = "https://www.niftyindices.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
FIRST_YEAR = 2011
WANTED = re.compile(
    r"^(changes?|replacements?) in (the )?(indices|index|nifty\b|s&p cnx|cnx|nifty midcap)|index changes"
    r"|^exclusions? (of|from)|replacements? in indices|^corporate adjustment .* replacement|^deferment of index|^index reconstitution", re.I)
SKIPPED = re.compile(r"fixed income|SME|IPO|corporate bond|bond", re.I)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    page = s.get(BASE + "/press-release", timeout=60)
    page.raise_for_status()
    items = [
        {"date": d, "path": p, "title": html.unescape(t).strip()}
        for d, p, t in re.findall(r"data-date=\"([^\"]+)\".*?href='([^']+)'[^>]*>([^<]+)</a>", page.text, re.S)
    ]
    log = {"fetched_at": datetime.now(UTC).isoformat(timespec="seconds"), "index_items": len(items),
           "index_page_sha256": sha256(page.content), "files": []}
    (OUT / "index.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")

    wanted = [i for i in items
              if int(i["date"][-4:]) >= FIRST_YEAR and WANTED.search(i["title"]) and not SKIPPED.search(i["title"])]
    log["selected"] = len(wanted)
    for n, it in enumerate(wanted, 1):
        dest = OUT / "pdf" / Path(it["path"]).name
        if dest.exists():
            body, status = dest.read_bytes(), "cached"
        else:
            for attempt in range(4):
                r = s.get(BASE + it["path"], timeout=60)
                if r.status_code == 200:
                    break
                time.sleep(2 + 2 * attempt)
            status, body = r.status_code, r.content
            if status == 200:
                dest.write_bytes(body)
            time.sleep(0.4)
        log["files"].append({"file": f"press_releases/pdf/{dest.name}", "date": it["date"], "title": it["title"],
                             "status": status, "bytes": len(body), "sha256": sha256(body) if status in (200, "cached") else None})
        if n % 50 == 0:
            print(n, "/", len(wanted))
    (HERE / "sources" / "fetch_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    bad = [f for f in log["files"] if f["status"] not in (200, "cached")]
    print("selected", len(wanted), "failed", len(bad))


if __name__ == "__main__":
    main()

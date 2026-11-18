"""Order-win study v2.1: shares outstanding from NSE's MCAP report.

    python scripts/order_win_shares_from_mcap.py

Reads research/announcements/order_wins/mcap/mcap17112026.csv (saved unchanged
from the Bhavcopy PR zip of 17-Nov-2026), checks its sha256 against the value
frozen in the v2.1 pre-registration, and writes
research/announcements/order_wins/shares_mcap17112026/shares.csv with columns
symbol, issued_size, series, source_sha256. No other transformation: fields
are whitespace-stripped, nothing is filtered or adjusted. Pass that file to
order_win_event_study.py --shares.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research" / "announcements" / "order_wins"
SRC = BASE / "mcap" / "mcap17112026.csv"
SRC_SHA256 = "a112794630c107f9480ef7ce555c93eef5c5f89056156afb3e0b3cc3bfafb8d8"
OUT = BASE / "shares_mcap17112026" / "shares.csv"


def main() -> None:
    raw = SRC.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SRC_SHA256:
        raise SystemExit(f"{SRC.name} changed: {actual} != {SRC_SHA256}")
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    out_rows, seen = [], set()
    for r in rows:
        r = {k.strip(): (v or "").strip() for k, v in r.items()}
        sym = r["Symbol"]
        if sym in seen:
            raise SystemExit(f"duplicate symbol in {SRC.name}: {sym}")
        seen.add(sym)
        out_rows.append({"symbol": sym, "issued_size": r["Issue Size"],
                         "series": r["Series"], "source_sha256": actual})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    print(f"{len(out_rows)} symbols -> {OUT}")


if __name__ == "__main__":
    main()

"""Build the liquid intraday universe (D3, decided 2026-10-25): median traded value (close x volume) over the
last 20 daily sessions >= 50 crore rupees. Read-only on the equity DB; writes research/intraday/universe.csv."""
from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_intel.persistence.connection import get_read_only_connection

MIN_MEDIAN_VALUE = 50 * 1e7  # 50 crore rupees
SESSIONS = 20


def main() -> int:
    conn = get_read_only_connection()
    conn.row_factory = lambda cur, row: {d[0]: row[i] for i, d in enumerate(cur.description)}
    run = conn.execute("SELECT run_id FROM acquired_observations ORDER BY trading_date DESC LIMIT 1").fetchone()
    if not run:
        print("No daily observations found."); return 1
    rows = conn.execute("SELECT symbol, instrument_key, trading_date, close, volume FROM acquired_observations "
                        "WHERE run_id=? ORDER BY symbol, trading_date", (run["run_id"],)).fetchall()
    by_sym: dict = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    keep = []
    for sym, rs in by_sym.items():
        last = rs[-SESSIONS:]
        if len(last) < SESSIONS:
            continue
        med = statistics.median(x["close"] * x["volume"] for x in last)
        if med >= MIN_MEDIAN_VALUE:
            keep.append((sym, last[-1]["instrument_key"], round(med / 1e7, 1)))
    out = ROOT / "research" / "intraday"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "universe.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["symbol", "instrument_key", "median_value_crore"])
        w.writerows(sorted(keep))
    print(f"{len(keep)} of {len(by_sym)} symbols pass the liquidity cut-off -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

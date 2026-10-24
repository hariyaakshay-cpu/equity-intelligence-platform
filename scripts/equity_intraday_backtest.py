"""Backtest the three pre-registered setups on cached 5-minute data. Read-only; writes
research/intraday/backtest_<date>.json. A PASS here is only a Stage-4 CANDIDATE: a walk-forward
run and sector check are still required before any signal is sent."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_intel.intraday.backtest import evaluate, run_setup
from equity_intel.intraday.setups import SETUPS, Bar

EXPECTED = 75


def load_sessions(cache: Path):
    sessions, dropped = {}, 0
    for p in sorted(cache.glob("*.csv")):
        days = {}
        with p.open() as f:
            for r in csv.DictReader(f):
                ts = datetime.fromisoformat(r["ts"])
                days.setdefault(ts.date().isoformat(), []).append(
                    Bar(ts, float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"])))
        good = {}
        for d, bars in days.items():
            bars.sort(key=lambda b: b.ts)
            if len(bars) == EXPECTED:
                good[d] = bars
            else:
                dropped += 1
        sessions[p.stem] = good
    return sessions, dropped


def main() -> int:
    cache = ROOT / "data" / "intraday_cache"
    sessions, dropped = load_sessions(cache)
    if not sessions:
        print("No cached data. Run equity_intraday_fetch.py first."); return 1
    report = {"run_at": datetime.now().isoformat(), "symbols": len(sessions),
              "sessions_dropped_incomplete": dropped, "setups": {}}
    for setup in SETUPS:
        report["setups"][setup] = evaluate(run_setup(setup, sessions))
        r = report["setups"][setup]
        print(f"{setup}: trades={r['trades']} verdict={r['verdict']} mean_net={r.get('mean_net_pct')}")
    out = ROOT / "research" / "intraday"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"backtest_{datetime.now():%Y-%m-%d}.json"
    path.write_text(json.dumps(report, indent=2))
    print("report:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

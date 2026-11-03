"""Evaluate the daily/swing pre-registration on DEV or (once) on HOLDOUT.

    python scripts/equity_daily_eval.py --split dev
    python scripts/equity_daily_eval.py --split holdout     # only lists that qualified on DEV; refuses to overwrite

Writes research/daily/result_<split>.json. Results are final and never overwritten.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_intel.scoring import daily_eval as de


def index_returns(path: Path, hold: int) -> dict:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    d, o, c = [r["date"] for r in rows], [float(r["o"]) for r in rows], [float(r["c"]) for r in rows]
    return {d[k]: c[k + hold] / o[k + 1] - 1.0 for k in range(len(d)) if k + hold < len(d) and o[k + 1] > 0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["dev", "holdout"], required=True)
    ap.add_argument("--dir", type=Path, default=ROOT / "research" / "daily")
    a = ap.parse_args(argv)
    out = a.dir / f"result_{a.split}.json"
    if out.exists():
        print(f"{out} already exists; results are final and are not overwritten"); return 1
    lists = list(de.LISTS)
    if a.split == "holdout":
        dev = json.loads((a.dir / "result_dev.json").read_text())
        lists = [n for n in lists if dev["lists"][n]["dev_qualifies_for_holdout"]]
        if not lists:
            print("no list qualified on DEV; HOLDOUT is not run"); return 1
    with (a.dir / f"replay_{a.split}.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    bench_file = ROOT / "data" / "daily_history" / "NIFTY500_INDEX.csv"
    result = {"split": a.split, "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "manifest": "research/daily/manifest_2026-11-03.sha256", "lists": {}}
    for name in lists:
        res = de.cohorts(rows, name, index_returns(bench_file, de.LISTS[name]))
        result["lists"][name] = de.summarize(res, name)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

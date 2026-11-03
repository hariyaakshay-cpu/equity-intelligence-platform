"""Run the pre-registered 12-1 momentum study.  python scripts/equity_momentum_12_1.py --split dev|holdout
Writes research/momentum/result_<split>.json once; refuses to overwrite; HOLDOUT only if DEV qualified."""
from __future__ import annotations

import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from equity_intel.scoring import momentum_12_1 as m

DEV = ("2022-10-06", "2025-08-05")
HOLDOUT = ("2025-09-05", "2026-10-28")


def _read(p: Path):
    d, o, c, v = [], [], [], []
    with p.open(newline="") as f:
        for r in csv.DictReader(f):
            try:
                vals = (float(r["o"]), float(r["c"]), float(r["v"]))
            except (ValueError, KeyError):
                continue
            d.append(r["date"]); o.append(vals[0]); c.append(vals[1]); v.append(vals[2])
    return d, o, c, v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "holdout"], required=True)
    a = ap.parse_args(argv)
    outd = ROOT / "research" / "momentum"
    out = outd / f"result_{a.split}.json"
    if out.exists():
        print(f"{out} exists; results are final"); return 1
    if a.split == "holdout" and not json.loads((outd / "result_dev.json").read_text())["summary"]["dev_qualifies_for_holdout"]:
        print("DEV did not qualify; HOLDOUT is not run"); return 1
    hist = ROOT / "data" / "daily_history"
    rows = []
    for p in sorted(hist.glob("*.csv")):
        if p.stem != "NIFTY500_INDEX":
            rows += m.symbol_rows(p.stem, *_read(p))
    d, o, c, _ = _read(hist / "NIFTY500_INDEX.csv")
    idx = {d[k]: c[k + m.HOLD] / o[k + 1] - 1.0 for k in range(len(d) - m.HOLD)}
    if a.split == "dev":
        keep = lambda r: DEV[0] <= r["date"] <= DEV[1] and r["exit_date"] < HOLDOUT[0]
    else:
        keep = lambda r: HOLDOUT[0] <= r["date"] <= HOLDOUT[1]
    s = m.summarize(m.cohorts(rows, keep, idx))
    res = {"split": a.split, "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "manifest": "research/momentum/manifest_2026-11-03.sha256", "summary": s}
    outd.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

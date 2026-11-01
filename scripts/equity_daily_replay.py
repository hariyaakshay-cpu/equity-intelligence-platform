"""Replay scoring v0 over data/daily_history/*.csv and write DEV and HOLDOUT score files.

    python scripts/equity_daily_replay.py                 # all symbols (a few minutes with 4 workers)
    python scripts/equity_daily_replay.py --symbols 360ONE,3MINDIA --out-dir C:/temp/replay_smoke   # smoke test

Writes research/daily/replay_dev.csv and replay_holdout.csv. Signal dates are split 70/30 with a purge gap of 20
sessions; dates in the gap are dropped. The HOLDOUT file is written here but is not read until a list qualifies on DEV.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_intel.features.config import load_config
from equity_intel.scoring.replay import replay_symbol

PURGE = 20
MIN_ROWS_PER_DATE = 100
FIELDS = ["date", "symbol", "short", "medium", "traded_value", "ret5", "excl5", "ret20", "excl20"]
_CFG = None
_BENCH = None


def _read(path: Path):
    cols = ([], [], [], [], [], [])
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            try:
                vals = [r["date"]] + [float(r[k]) for k in ("o", "h", "l", "c", "v")]
            except (ValueError, KeyError):
                continue
            for col, x in zip(cols, vals):
                col.append(x)
    return cols


def _init(cfg_path, bench_path):
    global _CFG, _BENCH
    _CFG = load_config(cfg_path)
    d, _, _, _, c, _ = _read(bench_path)
    _BENCH = dict(zip(d, c))


def _work(path):
    d, o, h, l, c, v = _read(Path(path))
    return replay_symbol(Path(path).stem, d, o, h, l, c, v, _BENCH, _CFG)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history-dir", type=Path, default=ROOT / "data" / "daily_history")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "research" / "daily")
    ap.add_argument("--symbols", help="comma-separated subset (smoke test)")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    a = ap.parse_args(argv)
    bench = a.history_dir / "NIFTY500_INDEX.csv"
    if not bench.exists():
        print("NIFTY500_INDEX.csv is missing: finish scripts/equity_daily_history_fetch.py first"); return 1
    files = sorted(p for p in a.history_dir.glob("*.csv") if p.stem != "NIFTY500_INDEX")
    if a.symbols:
        want = set(a.symbols.split(","))
        files = [p for p in files if p.stem in want]
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(ROOT / "config" / "indicators_v1.json", bench)) as ex:
        rows = [r for part in ex.map(_work, map(str, files), chunksize=4) for r in part]
    counts = {}
    for r in rows:
        counts[r["date"]] = counts.get(r["date"], 0) + 1
    dates = sorted(d for d, n in counts.items() if n >= MIN_ROWS_PER_DATE) if not a.symbols else sorted(counts)
    cut = int(len(dates) * 0.7)
    dev, hold = set(dates[:cut]), set(dates[cut + PURGE:])
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for name, keep in (("replay_dev.csv", dev), ("replay_holdout.csv", hold)):
        with (a.out_dir / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(r for r in rows if r["date"] in keep)
    print(f"{len(files)} symbols, {len(rows)} scored symbol-dates, {len(dates)} signal dates; "
          f"DEV {len(dev)} dates, purge {PURGE}, HOLDOUT {len(hold)} dates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

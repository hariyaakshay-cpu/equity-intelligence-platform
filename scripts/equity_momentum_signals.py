"""Write today's 12-1 momentum list for the dashboard (NOT VALIDATED, no target / stop-loss).

    python scripts/equity_daily_history_fetch.py --start 2025-06-01 --out-dir data/daily_live --refresh
    python scripts/equity_momentum_signals.py

Reads --history-dir (default data/daily_live, kept apart from the frozen research data/daily_history), takes the
as-of date from NIFTY500_INDEX.csv, writes data/signals/momentum_12_1_<asof>.json. An existing file for the same
date is never overwritten.
"""
from __future__ import annotations

import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from equity_intel.scoring.momentum_live import MIN_COVERAGE, choose_asof, cut_to, latest_list


def _read(p: Path):
    d, o, c, v = [], [], [], []
    with p.open(newline="") as f:
        for r in csv.DictReader(f):
            try:
                x = (float(r["o"]), float(r["c"]), float(r["v"]))
            except (ValueError, KeyError):
                continue
            d.append(r["date"]); o.append(x[0]); c.append(x[1]); v.append(x[2])
    return d, o, c, v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history-dir", type=Path, default=ROOT / "data" / "daily_live")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "signals")
    a = ap.parse_args(argv)
    idx = a.history_dir / "NIFTY500_INDEX.csv"
    if not idx.exists():
        print(f"{idx} missing: run the fetch command in this script's docstring first"); return 1
    series = {p.stem: _read(p) for p in sorted(a.history_dir.glob("*.csv")) if p.stem != "NIFTY500_INDEX"}
    asof = choose_asof([d[-1] for d, _o, _c, _v in series.values() if d])
    newest = _read(idx)[0][-1]
    if asof is None:
        print("no date reaches the coverage floor; nothing written"); return 1
    if asof != newest:
        print(f"newest session {newest} is not yet published for {MIN_COVERAGE:.0%} of symbols; using {asof}")
    out = a.out_dir / f"momentum_12_1_{asof}.json"
    if out.exists():
        print(f"{out} already exists; not overwritten"); return 0
    series = cut_to(series, asof)
    body = latest_list(series, asof)
    body["generated_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body["history_dir"] = str(a.history_dir.relative_to(ROOT)) if a.history_dir.is_relative_to(ROOT) else str(a.history_dir)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=1))
    print(f"{out.name}: {len(body['picks'])} picks from {body['eligible']} eligible "
          f"(stale {body['skipped_stale']}, short history {body['skipped_short_history']}, illiquid {body['skipped_illiquid']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

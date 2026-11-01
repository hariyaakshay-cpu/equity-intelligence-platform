"""Round-3 intraday research with a held-out period (see ..._setups_v2_preregistration_DRAFT.md).

    python scripts/equity_intraday_round3.py dev        # diagnostics on first 70% of sessions
    python scripts/equity_intraday_round3.py holdout    # ONCE per setup, only setups with DEV mean net > 0
Reports show gross and net per trade. Costs are the ASSUMED COSTS table (not verified).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from equity_intel.intraday.backtest import evaluate
from equity_intel.intraday.round3 import ROUND3_SETUPS, market_context, run_round3
from equity_intraday_backtest import load_sessions

BONFERRONI_ALPHA = 0.05 / 9  # nine setups tried in total (6 + 3)


def _report(trades, **kw) -> dict:
    rep = evaluate(trades, **kw)
    if trades:
        rep["mean_gross_pct"] = sum(t["gross_pct"] for t in trades) / len(trades)
    return rep


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("dev", "holdout"):
        print(__doc__); return 2
    sessions, _ = load_sessions(ROOT / "data" / "intraday_cache")
    ctx = market_context(sessions)
    all_dates = sorted({d for days in sessions.values() for d in days})
    cut = int(len(all_dates) * 0.7)
    dev, hold = set(all_dates[:cut]), set(all_dates[cut:])
    out_dir = ROOT / "research" / "intraday"
    out_dir.mkdir(parents=True, exist_ok=True)
    dev_path, hold_path = out_dir / "round3_dev.json", out_dir / "round3_holdout.json"
    if mode == "dev":
        rep = {s: _report(run_round3(s, sessions, ctx, dev)) for s in ROUND3_SETUPS}
        dev_path.write_text(json.dumps(rep, indent=2))
        for s, r in rep.items():
            print(f"DEV {s}: trades={r['trades']} gross={r.get('mean_gross_pct')} net={r.get('mean_net_pct')} verdict={r['verdict']}")
        return 0
    if hold_path.exists():
        print("Holdout already run; result is final and will not be overwritten:", hold_path); return 1
    devrep = json.loads(dev_path.read_text())
    rep = {}
    for s in ROUND3_SETUPS:
        if devrep[s].get("mean_net_pct", -1) <= 0:
            rep[s] = {"skipped": "DEV mean net <= 0 (not advanced)"}; continue
        rep[s] = _report(run_round3(s, sessions, ctx, hold), ci_alpha=BONFERRONI_ALPHA, min_trades=100, min_sessions=30)
    hold_path.write_text(json.dumps(rep, indent=2))
    for s, r in rep.items():
        print(f"HOLDOUT {s}: {r.get('verdict', r.get('skipped'))} trades={r.get('trades')} net={r.get('mean_net_pct')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

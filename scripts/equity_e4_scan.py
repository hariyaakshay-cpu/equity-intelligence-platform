"""Run the E4 data-only feature scan over the latest stored E1-E3 run."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_intel.features.config import load_config
from equity_intel.features.runner import run_feature_scan


def main() -> int:
    cfg = load_config(ROOT / "config/indicators_v1.json")
    summary = run_feature_scan(cfg, db_path=ROOT / "data/equity_intel.db")
    print(summary)
    if summary["stale_adjustment_basis"]:
        print(f"WARNING: {len(summary['stale_adjustment_basis'])} symbol(s) have a corporate action effective on/after "
              f"acquisition run {summary['acquisition_run_id']} was fetched; features withheld (ADJUSTMENT_BASIS_STALE). "
              "Re-run scripts/equity_data_acquisition.py, then this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

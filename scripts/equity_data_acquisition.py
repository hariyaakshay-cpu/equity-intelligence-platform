"""Run the E1-E3 research-only Equity Intelligence acquisition pipeline."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Settings
from core.providers import UpstoxProvider
from equity_intel.acquisition.runner import run_equity_data_acquisition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=ROOT / "data/reference/nifty500_constituents_2026-09-24.csv")
    parser.add_argument("--instrument-master", type=Path, default=ROOT / "data/reference/upstox_NSE_instruments_2026-09-24.json.gz")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--required-sessions", type=int, default=252)
    args = parser.parse_args()
    try:
        provider = UpstoxProvider(Settings())
    except ValueError as error:
        parser.error(f"Upstox configuration unavailable: {error}")
    report = run_equity_data_acquisition(provider, args.universe, args.instrument_master,
        start_date=args.start_date, end_date=args.end_date, required_sessions=args.required_sessions,
        db_path=ROOT / "data/equity_intel.db", report_dir=ROOT / "data/equity_intel/reports")
    print(f"Run {report.run_id}: {report.status}; universe {report.universe_count}; mapped {report.mapped_count}; "
          f"persisted {report.persisted_symbol_count} symbols / {report.persisted_observation_count} observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

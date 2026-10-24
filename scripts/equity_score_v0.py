"""PROVISIONAL v0: score the latest COMPLETE E4 scan and persist the result.

Run after scripts/equity_e4_scan.py. Writes only e4_provisional_scores in
data/equity_intel.db. Scores are labelled PROVISIONAL - not B2-authoritative.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from equity_intel.persistence.connection import connect
from equity_intel.scanner.execution_guard import assert_no_forbidden_modules_loaded
from equity_intel.scoring import persist_v0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-id", default=None, help="E4 scan id (default: latest COMPLETE)")
    args = parser.parse_args(argv)
    assert_no_forbidden_modules_loaded()
    connection = connect(ROOT / "data/equity_intel.db")
    try:
        scan_id = args.scan_id
        if scan_id is None:
            latest = persist_v0.latest_complete_scan(connection)
            if latest is None:
                print("No COMPLETE E4 scan found; run scripts/equity_e4_scan.py first.")
                return 1
            scan_id = latest["scan_id"]
        print(persist_v0.score_scan(connection, scan_id))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

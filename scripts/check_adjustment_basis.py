"""Read-only check: are Upstox daily candles adjusted for a known split/bonus?

    python scripts/check_adjustment_basis.py --symbol SYMBOL --ex-date YYYY-MM-DD --price-divisor 2

Fetches daily candles around the ex-date through the scanner's own
fetch_symbol_candles and prints the closes either side of it. It writes no
database row, no snapshot and no ScanRun, and changes no scan behaviour. It does
download the instrument master and save it under data/reference/.
"""
import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import Settings
from core.providers.upstox_provider import UpstoxProvider
from equity_intel.config import IST
from equity_intel.scanner.acquisition import AuthFailedError, fetch_symbol_candles
from equity_intel.scanner.adjustment_check import compare_across_event
from equity_intel.scanner.instrument_master import fetch_instrument_master
from equity_intel.scanner.instrument_mapping import map_universe_isins
from equity_intel.scanner.universe import load_universe

DATA_REFERENCE_DIR = REPO_ROOT / "data" / "reference"


def _candle_date(candle) -> date:
    ts = candle.timestamp
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            ts = ts.astimezone(IST)
        return ts.date()
    return ts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--ex-date", required=True, type=date.fromisoformat)
    parser.add_argument("--price-divisor", required=True, type=float,
                        help="Factor the price is divided by at the ex-date (1:1 bonus or 2-for-1 split = 2).")
    parser.add_argument("--window-days", type=int, default=10,
                        help="Calendar days of candles to fetch on each side of the ex-date.")
    args = parser.parse_args(argv)

    csvs = sorted(DATA_REFERENCE_DIR.glob("nifty500_constituents_*.csv"))
    if not csvs:
        print(f"Error: no nifty500_constituents_*.csv under {DATA_REFERENCE_DIR}")
        return 1
    universe = load_universe(csvs[-1])
    member = next((m for m in universe.members if m.symbol == args.symbol), None)
    if member is None:
        print(f"Error: {args.symbol} is not in the universe")
        return 1

    now = datetime.now(IST)
    master = fetch_instrument_master(DATA_REFERENCE_DIR, now=now)
    mapping, _ = map_universe_isins(master, [member.isin])
    instrument_key = mapping.isin_to_instrument_key.get(member.isin)
    if instrument_key is None:
        print(f"Error: no instrument key for {args.symbol} (ISIN {member.isin})")
        return 1

    start = datetime.combine(args.ex_date - timedelta(days=args.window_days), datetime.min.time(), tzinfo=IST)
    end = datetime.combine(args.ex_date + timedelta(days=args.window_days), datetime.min.time(), tzinfo=IST)
    provider = UpstoxProvider(Settings())
    try:
        candles, error = fetch_symbol_candles(provider, instrument_key, start, end)
    except AuthFailedError:
        print("Upstox rejected the access token (401). Refresh UPSTOX_ACCESS_TOKEN and re-run.")
        return 1
    if error:
        print(f"Error fetching candles: {error}")
        return 1

    result = compare_across_event(
        [(_candle_date(c), c.close) for c in candles], args.ex_date, args.price_divisor
    )
    print(f"symbol={args.symbol} instrument_key={instrument_key} candles={len(candles)}")
    print(f"ex_date={result.ex_date} price_divisor={result.price_divisor}")
    if not result.conclusive:
        print(f"INCONCLUSIVE: before={result.date_before} on_or_after={result.date_on_or_after} "
              "(need a session on each side of the ex-date within the window)")
        return 2
    print(f"before      {result.date_before}  close={result.close_before}")
    print(f"on/after    {result.date_on_or_after}  close={result.close_on_or_after}")
    print(f"observed_ratio={result.observed_ratio:.4f}")
    print(f"  adjusted data would be near 1.0000        (distance {result.distance_to_adjusted:.4f})")
    print(f"  unadjusted data would be near {result.unadjusted_expected_ratio:.4f}   (distance {result.distance_to_unadjusted:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Phase 1 intraday data probe (read-only). Run on your PC with your Upstox token.

Asks Upstox for 5-minute candles over several window lengths for a few liquid
symbols plus the Nifty 500 index, and records what comes back (or the exact
error). Writes ONE JSON report to research/intraday/ and prints a short
summary. It writes to no database, places no orders, and never prints the
token. Spend: about 20 API calls with a pause between them.

Usage:
    python scripts/equity_intraday_probe.py
    python scripts/equity_intraday_probe.py --keys "NSE_EQ|INE002A01018,NSE_INDEX|Nifty 500"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Settings
from core.providers.upstox_provider import UpstoxProvider
from equity_intel.intraday.probe import IST, last_weekday_on_or_before, summarize_candles
from equity_intel.scanner.execution_guard import assert_no_forbidden_modules_loaded

# Defaults are well-known ISINs; a wrong key shows up in the report as an error, not a guess.
DEFAULT_KEYS = ["NSE_EQ|INE002A01018", "NSE_EQ|INE467B01029", "NSE_EQ|INE009A01021", "NSE_EQ|INE040A01034",
                "NSE_INDEX|Nifty 500"]
WINDOW_DAYS = [1, 5, 30, 31, 90, 400]
PAUSE_SECONDS = 0.7


def _try(label, fn):
    started = time.time()
    try:
        value = fn()
        return {"label": label, "ok": True, "seconds": round(time.time() - started, 2), "value": value}
    except Exception as exc:  # the exact failure is the finding
        return {"label": label, "ok": False, "seconds": round(time.time() - started, 2),
                "error_type": type(exc).__name__, "error": str(exc)[:400]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keys", default=None, help="comma-separated Upstox instrument keys")
    args = parser.parse_args(argv)
    assert_no_forbidden_modules_loaded()
    keys = [k.strip() for k in args.keys.split(",")] if args.keys else DEFAULT_KEYS
    provider = UpstoxProvider(Settings())
    now = datetime.now(timezone.utc)
    end = last_weekday_on_or_before(now.astimezone(IST)).astimezone(timezone.utc)
    report = {"probed_at": now.astimezone(IST).isoformat(), "bar": "5minute", "window_end": end.isoformat(),
              "note": "weekday approximation only; NSE holidays unknown", "probes": []}
    for key in keys:
        for days in WINDOW_DAYS:
            start = end - timedelta(days=days)
            def run(key=key, start=start):
                return summarize_candles(provider.get_historical_data(key, "5minute", start, end), now)
            result = _try(f"{key} historical {days}d", run)
            result["instrument_key"], result["window_days"] = key, days
            report["probes"].append(result)
            time.sleep(PAUSE_SECONDS)
        # today's session via the intraday endpoint (existence/limits unverified: the error text is the answer)
        def run_intraday(key=key):
            endpoint = f"historical-candle/intraday/{quote(key, safe='')}/minutes/5"
            data = provider._make_api_request("GET", endpoint)
            raw = data.get("data", {}).get("candles", [])
            return {"raw_candles": len(raw), "first_row": raw[0] if raw else None, "last_row": raw[-1] if raw else None}
        result = _try(f"{key} intraday endpoint", run_intraday)
        result["instrument_key"], result["window_days"] = key, "today"
        report["probes"].append(result)
        time.sleep(PAUSE_SECONDS)
    out_dir = ROOT / "research" / "intraday"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"upstox_5min_probe_{now.astimezone(IST).strftime('%Y%m%dT%H%M')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    ok = sum(1 for p in report["probes"] if p["ok"])
    print(f"{ok}/{len(report['probes'])} probes returned data; report: {out}")
    for p in report["probes"]:
        status = "ok " if p["ok"] else "ERR"
        detail = (f"{p['value'].get('candle_count', p['value'].get('raw_candles'))} bars" if p["ok"]
                  else f"{p['error_type']}: {p['error'][:90]}")
        print(f"  [{status}] {p['label']}: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

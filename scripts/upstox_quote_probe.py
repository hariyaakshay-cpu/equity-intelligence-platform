"""One read-only Upstox market-quote request, raw reply saved (paper board, step 2 check).

    python scripts/upstox_quote_probe.py

Requests full quotes for 3 symbols from the documented v2 endpoint
GET https://api.upstox.com/v2/market-quote/quotes?instrument_key=...
and saves the unmodified JSON to data/paper_board/probe_<ts>.json.
No orders; nothing else is called.
"""
from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import Settings  # noqa: E402

URL = "https://api.upstox.com/v2/market-quote/quotes"
SYMBOLS = ["KEC", "BEL", "INFY"]


def main() -> None:
    token = Settings().UPSTOX_ACCESS_TOKEN
    if not token:
        raise SystemExit("UPSTOX_ACCESS_TOKEN missing: run scripts/upstox_auth.py first")
    newest = sorted((ROOT / "data" / "reference").glob("upstox_NSE_instruments_*.json.gz"))[-1]
    keys = {r["trading_symbol"]: r["instrument_key"] for r in json.load(gzip.open(newest))
            if r.get("segment") == "NSE_EQ"}
    wanted = [keys[s] for s in SYMBOLS if s in keys]
    resp = requests.get(URL, params={"instrument_key": ",".join(wanted)},
                        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                        timeout=20)
    out = ROOT / "data" / "paper_board" / f"probe_{datetime.now():%Y%m%dT%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    print(f"HTTP {resp.status_code}; keys asked {wanted}; saved {out}")
    try:
        data = resp.json().get("data", {})
        for k, v in data.items():
            print(k, {f: v.get(f) for f in ("instrument_token", "last_price", "volume", "ohlc", "timestamp")})
    except ValueError:
        print(resp.text[:300])


if __name__ == "__main__":
    main()

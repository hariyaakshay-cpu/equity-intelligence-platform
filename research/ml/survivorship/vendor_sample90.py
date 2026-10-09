"""Bounded Upstox check: first/last daily bar for a fixed 90-symbol sample (spec 5A.2 items 1 and 4).

RESEARCH ONLY — NOT A TRADING RECOMMENDATION.

Approved scope (replaces the unbounded vendor_first_bars.py run):
  - 90 current constituents, chosen deterministically: snapshot rows sorted by (Industry,
    sha256(SEED + symbol)), every k-th row. No random generator.
  - Symbols already present in sources/vendor_first_bars.json are reused, not refetched.
  - 3 five-year windows per fetched symbol (2011-2015, 2016-2020, 2021-2026): at most 270 calls.
  - Up to 30 names that left the Nifty 500 since 2020-03-27 and resolve by trading symbol in the
    newest local Upstox instrument master, chosen the same way: at most 90 calls.
  - GET historical-candle only, through UpstoxProvider (token from UPSTOX_ACCESS_TOKEN via Settings).
  - Pace: one call per second. Stop at the first of: two consecutive HTTP 429 after a 30 s backoff,
    any authentication error, 500 calls, 30 minutes.
  - The database is not opened: instrument keys come from the snapshot ISINs (NSE_EQ|<ISIN>) and the
    local instrument master.
Writes only sources/vendor_sample90.json (bar dates are not stored, only first/last/count/hash).

Run from the repository root that holds .env and data/:
    python <path>/vendor_sample90.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import glob
import gzip
import hashlib
import json
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sources" / "vendor_sample90.json"
PRIOR = HERE / "sources" / "vendor_first_bars.json"
EVENTS = HERE / "nifty500_events.csv"
SNAPSHOT = "data/reference/nifty500_constituents_2026-09-24.csv"
SEED = "survivorship-sample-v1"
N_SAMPLE, N_REMOVED = 90, 30
WINDOWS = [(2011, 2016), (2016, 2021), (2021, 2026)]    # [from year, to year); last one ends 2026-10-02
END = date(2026, 10, 2)
MAX_CALLS, MAX_SECONDS = 500, 30 * 60


def pick(items: list[tuple[str, str]], n: int) -> list[str]:
    """items = (group, symbol). Sort by (group, hash), take every k-th."""
    ordered = sorted(items, key=lambda x: (x[0], hashlib.sha256((SEED + x[1]).encode()).hexdigest()))
    step = len(ordered) / n
    return [ordered[int(i * step)][1] for i in range(min(n, len(ordered)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(SNAPSHOT, encoding="utf-8")))
    isin = {r["Symbol"]: r["ISIN Code"] for r in rows}
    sample = pick([(r["Industry"], r["Symbol"]) for r in rows], N_SAMPLE)

    master_path = sorted(glob.glob("data/reference/upstox_NSE_instruments_*.json.gz"))[-1]
    master_sha = hashlib.sha256(Path(master_path).read_bytes()).hexdigest()
    eq = {r["trading_symbol"]: r["instrument_key"] for r in json.load(gzip.open(master_path))
          if r.get("segment") == "NSE_EQ" and r.get("instrument_type") == "EQ"}
    events = list(csv.DictReader(EVENTS.open(encoding="utf-8")))
    left = sorted({r["symbol"] for r in events if r["action"] == "EXCLUDE" and r["effective_date"] >= "2020-03-27"}
                  - set(isin))
    resolvable = [s for s in left if s in eq]
    removed = pick([("", s) for s in resolvable], N_REMOVED)

    prior = json.loads(PRIOR.read_text(encoding="utf-8"))["symbols"] if PRIOR.exists() else {}
    reuse = {s: prior[s] for s in sample if s in prior and not prior[s]["error"]}
    todo = [("current", s, f"NSE_EQ|{isin[s]}") for s in sample if s not in reuse]
    todo += [("removed", s, eq[s]) for s in removed]
    print(f"sample {len(sample)} (reused {len(reuse)}, to fetch {len(todo) - len(removed)}), removed names {len(removed)}, "
          f"planned calls <= {len(todo) * len(WINDOWS)}")
    if args.dry_run:
        print("sample:", " ".join(sample))
        print("removed:", " ".join(removed))
        return

    sys.path.insert(0, str(Path.cwd()))
    from config import Settings
    from core.providers import UpstoxProvider

    provider = UpstoxProvider(Settings())
    result = {"started_at": datetime.now(UTC).isoformat(timespec="seconds"), "seed": SEED,
              "instrument_master": master_path, "instrument_master_sha256": master_sha,
              "sample": sample, "removed_sample": removed, "removed_unresolved": sorted(set(left) - set(resolvable)),
              "reused_from_vendor_first_bars": sorted(reuse), "symbols": dict(reuse), "removed": {},
              "calls": 0, "stopped": None}
    t0, consecutive_429 = time.monotonic(), 0

    def save():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")

    def stop(reason: str) -> None:
        result["stopped"] = reason
        save()
        print("STOPPED:", reason, "calls", result["calls"])
        sys.exit(0)

    for kind, symbol, key in todo:
        dates: set[str] = set()
        failed: list[str] = []
        for y0, y1 in WINDOWS:
            end = min(date(y1, 1, 1), END)
            for attempt in range(2):
                if result["calls"] >= MAX_CALLS:
                    stop("500 calls reached")
                if time.monotonic() - t0 > MAX_SECONDS:
                    stop("30 minutes elapsed")
                result["calls"] += 1
                time.sleep(1.0)
                try:
                    candles = provider.get_historical_data(key, "1day", datetime(y0, 1, 1, tzinfo=UTC),
                                                           datetime(end.year, end.month, end.day, tzinfo=UTC))
                    dates |= {c.timestamp.date().isoformat() for c in candles if c.timestamp}
                    consecutive_429 = 0
                    break
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    if "AuthenticationError" in msg or "HTTP 401" in msg or "HTTP 403" in msg:
                        stop(f"authentication error on {symbol}")
                    if "429" in msg:
                        if attempt == 0:
                            time.sleep(30)
                            continue
                        consecutive_429 += 1
                        if consecutive_429 >= 2:
                            stop(f"two consecutive HTTP 429 after backoff (at {symbol})")
                    failed.append(f"{y0}-{y1}: {msg[:100]}")
                    break
        ds = sorted(dates)
        entry = {"instrument_key": key, "first_bar": ds[0] if ds else None, "last_bar": ds[-1] if ds else None,
                 "bars": len(ds), "dates_sha256": hashlib.sha256("\n".join(ds).encode()).hexdigest(),
                 "windows": "2011-2026", "error": "; ".join(failed) or None}
        (result["symbols"] if kind == "current" else result["removed"])[symbol] = entry
        save()
    result["stopped"] = "complete"
    result["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    save()
    print("complete, calls", result["calls"])


if __name__ == "__main__":
    main()

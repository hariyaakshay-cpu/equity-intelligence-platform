"""Read-only Upstox daily-history availability check for a fixed symbol list.

RESEARCH ONLY -- NOT A TRADING RECOMMENDATION.

    python scripts/universe_history_check.py --symbols-csv PATH/membership_intervals_v1.csv

Selects the rows of --symbols-csv whose vendor_status is RESOLVED (exactly 90
expected), fetches daily candles for each unique instrument_key through
UpstoxProvider (historical-candle GET only), and writes two NEW files under
research/ml/universe/:

    history_check_v1.csv       one row per input row (duplicates share a fetch)
    history_check_v1_run.json  run metadata

It reports facts only: first/last bar, bar count, gaps against the verified NSE
session calendar, zero-volume bars, and whether data was returned. It applies no
threshold, STALE rule or score. It opens no database and imports no broker or
trading module.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.providers.upstox_provider import UpstoxProvider
from equity_intel.config import IST
from equity_intel.scanner.acquisition import AuthFailedError, RateLimiter, fetch_symbol_candles

OUTPUT_DIR = REPO_ROOT / "research" / "ml" / "universe"
CSV_NAME = "history_check_v1.csv"
RUN_JSON_NAME = "history_check_v1_run.json"
CALENDAR_PATH = REPO_ROOT / "research" / "ml" / "calendar" / "nse_equity_calendar_v1.csv"
CALENDAR_MANIFEST_PATH = REPO_ROOT / "research" / "ml" / "calendar" / "calendar_manifest_v1.json"

SELECTED_VENDOR_STATUS = "RESOLVED"
MAX_SYMBOLS = 90
HISTORY_FLOOR = date(2000, 1, 1)
WINDOW_DAYS = 3650  # V3 refuses a daily window of more than one decade
MAX_WINDOWS = 3  # 3 x 3650 days back from today covers the 2000-01-01 floor
PER_SYMBOL_DEADLINE_S = 60.0
REQUESTS_PER_SECOND = 2.0

CSV_FIELDS = ["symbol", "instrument_key", "first_bar", "last_bar", "bars", "gap_count",
              "zero_volume_bars", "status", "error"]
STATUS_DATA = "DATA_RETURNED"
STATUS_NO_DATA = "NO_DATA"
STATUS_ERROR = "ERROR"

CALENDAR_NOTE = (
    "Gaps are measured against the verified NSE equity session calendar "
    "(nse_equity_calendar_v1.csv, is_session=1), a deliberate departure from the 2026-09-27 "
    "wording that Nifty 500 candles are the primary calendar. The index feed has a known vendor "
    "gap on 2020-01-07 (a regular session). NSE_INDEX|Nifty 500 was not fetched in this run."
)


TOKEN_VAR = "UPSTOX_ACCESS_TOKEN"


class TokenOnly:
    """The one attribute UpstoxProvider reads from its settings object. Deliberately not
    config.settings.Settings: that class reads a cwd .env implicitly and its validation
    errors echo the values of unrelated keys. repr/str never show the token."""

    def __init__(self, token: str):
        self.UPSTOX_ACCESS_TOKEN = token

    def __repr__(self):
        return "TokenOnly(UPSTOX_ACCESS_TOKEN=<redacted>)"


def load_token(env_file=None, environ=None) -> TokenOnly:
    """--env-file if given, else the process environment. Never reads a cwd .env. Error
    messages name the source, never a value."""
    if env_file is not None:
        if not Path(env_file).is_file():
            raise ValueError(f"--env-file {env_file} is not a file")
        token = dotenv_values(env_file).get(TOKEN_VAR)
        source = f"--env-file {env_file}"
    else:
        token = (os.environ if environ is None else environ).get(TOKEN_VAR)
        source = "the process environment"
    if not token:
        raise ValueError(f"{TOKEN_VAR} not found in {source}")
    return TokenOnly(token)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_selection(symbols_csv: Path) -> list:
    """Return [(symbol, instrument_key), ...] for the RESOLVED rows, in file order."""
    with open(symbols_csv, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("vendor_status") == SELECTED_VENDOR_STATUS]
    if len(rows) > MAX_SYMBOLS:
        raise ValueError(f"{len(rows)} rows selected; hard cap is {MAX_SYMBOLS}")
    selection = [(r["symbol"], r["instrument_key"]) for r in rows]
    keys_by_symbol = {}
    for symbol, key in selection:
        if not key:
            raise ValueError(f"{symbol}: empty instrument_key")
        keys_by_symbol.setdefault(symbol, set()).add(key)
    ambiguous = {s: sorted(k) for s, k in keys_by_symbol.items() if len(k) > 1}
    if ambiguous:
        raise ValueError(f"ambiguous symbol-to-instrument_key mapping: {ambiguous}")
    return selection


def load_sessions(calendar_csv: Path) -> list:
    """Sorted list of session dates (is_session == 1)."""
    with open(calendar_csv, newline="", encoding="utf-8") as fh:
        return sorted(date.fromisoformat(r["date"]) for r in csv.DictReader(fh) if r["is_session"] == "1")


def _candle_date(candle):
    ts = candle.timestamp
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            ts = ts.astimezone(IST)
        return ts.date()
    return ts


def summarize(candles: list, sessions: list) -> dict:
    """Facts about one symbol's candles. gap_count counts calendar sessions between
    first_bar and last_bar (inclusive, clipped to the calendar span) with no bar."""
    dated = [(_candle_date(c), c) for c in candles]
    dates = sorted({d for d, _ in dated if d is not None})
    zero_volume = sum(1 for _, c in dated if not c.volume)
    out = {"first_bar": dates[0] if dates else None, "last_bar": dates[-1] if dates else None,
           "bars": len(dates), "zero_volume_bars": zero_volume, "gap_count": None,
           "non_session_bars": 0, "undated_candles": sum(1 for d, _ in dated if d is None)}
    if not dates:
        return out
    present = set(dates)
    in_span = [s for s in sessions if dates[0] <= s <= dates[-1]]
    out["gap_count"] = sum(1 for s in in_span if s not in present)
    session_set = set(sessions)
    cal_start, cal_end = sessions[0], sessions[-1]
    out["non_session_bars"] = sum(1 for d in dates if cal_start <= d <= cal_end and d not in session_set)
    return out


def fetch_all_windows(provider, key: str, today: date, limiter, clock=time.monotonic):
    """(candles, error). Fixed number of decade windows back from `today`; no early stop
    (a delisted name has an empty latest window but earlier history). Any window error or
    deadline overrun makes the whole symbol ERROR. A 401 raises AuthFailedError."""
    started = clock()
    candles = []
    window_end = today
    for _ in range(MAX_WINDOWS):
        if window_end < HISTORY_FLOOR:
            break
        if clock() - started > PER_SYMBOL_DEADLINE_S:
            return [], f"per-symbol deadline of {PER_SYMBOL_DEADLINE_S:.0f}s exceeded"
        window_start = max(HISTORY_FLOOR, window_end - timedelta(days=WINDOW_DAYS))
        limiter.wait()
        got, error = fetch_symbol_candles(
            provider, key,
            datetime.combine(window_start, datetime.min.time(), tzinfo=IST),
            datetime.combine(window_end, datetime.min.time(), tzinfo=IST),
        )
        if error is not None:
            return [], f"window {window_start}..{window_end}: {error}"
        candles.extend(got)
        window_end = window_start - timedelta(days=1)
    return candles, None


def check_symbols(provider, selection: list, sessions: list, today: date, limiter, clock=time.monotonic):
    """Return (rows, results_by_key, aborted_reason). One failure never stops the run;
    a 401 aborts it. Duplicate keys reuse the first fetch."""
    results = {}
    rows = []
    aborted = None
    for symbol, key in selection:
        if key not in results:
            try:
                candles, error = fetch_all_windows(provider, key, today, limiter, clock)
            except AuthFailedError as exc:
                aborted = f"AUTH_FAILED: {exc}"
                break
            if error is not None:
                results[key] = {"status": STATUS_ERROR, "error": error, "first_bar": None, "last_bar": None,
                                "bars": None, "gap_count": None, "zero_volume_bars": None,
                                "non_session_bars": 0, "undated_candles": 0}
            else:
                facts = summarize(candles, sessions)
                results[key] = {**facts, "status": STATUS_DATA if facts["bars"] else STATUS_NO_DATA, "error": ""}
        rows.append({"symbol": symbol, "instrument_key": key, **results[key]})
    return rows, results, aborted


def _csv_value(v):
    return "" if v is None else v.isoformat() if isinstance(v, date) else v


def write_outputs(out_dir: Path, rows: list, meta: dict) -> None:
    """Create the two output files. Refuses any directory other than OUTPUT_DIR and any
    existing file (mode 'x'): new files only."""
    if Path(out_dir).resolve() != OUTPUT_DIR.resolve():
        raise ValueError(f"outputs must go to {OUTPUT_DIR}, not {out_dir}")
    out_dir = Path(out_dir)
    with open(out_dir / CSV_NAME, "x", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_value(row.get(k)) for k in CSV_FIELDS})
    with open(out_dir / RUN_JSON_NAME, "x", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=1)
        fh.write("\n")


def build_meta(*, started, finished, today, selection, rows, results, aborted, symbols_csv, sessions) -> dict:
    manifest = json.loads(CALENDAR_MANIFEST_PATH.read_text(encoding="utf-8"))
    counts = {s: sum(1 for r in results.values() if r["status"] == s)
              for s in (STATUS_DATA, STATUS_NO_DATA, STATUS_ERROR)}
    return {
        "label": "RESEARCH ONLY - NOT A TRADING RECOMMENDATION",
        "run_started_utc": started.isoformat(),
        "run_finished_utc": finished.isoformat(),
        "aborted": aborted,
        "source": "Upstox V3 historical-candle GET via core.providers.upstox_provider.UpstoxProvider "
                  "(interval 1day; request construction fixed in 4c27a66)",
        "request_window": {"history_floor": HISTORY_FLOOR.isoformat(), "to_date": today.isoformat(),
                           "window_days": WINDOW_DAYS, "windows_per_symbol": MAX_WINDOWS},
        "bounds": {"max_symbols": MAX_SYMBOLS, "per_symbol_deadline_s": PER_SYMBOL_DEADLINE_S,
                   "requests_per_second": REQUESTS_PER_SECOND,
                   "provider_retry": "up to 3 attempts per request on 429/5xx/transport errors (provider-internal)"},
        "symbols_csv": {"path": str(symbols_csv), "sha256": sha256_file(symbols_csv),
                        "selection": f"vendor_status == {SELECTED_VENDOR_STATUS}"},
        "rows": len(selection),
        "unique_keys": len({k for _, k in selection}),
        "rows_written": len(rows),
        "status_counts_unique_keys": counts,
        "bars_on_non_session_dates_total": sum(r["non_session_bars"] for r in results.values()),
        "undated_candles_total": sum(r["undated_candles"] for r in results.values()),
        "calendar": {"path": "research/ml/calendar/nse_equity_calendar_v1.csv",
                     "sha256": sha256_file(CALENDAR_PATH),
                     "manifest": "research/ml/calendar/calendar_manifest_v1.json",
                     "manifest_sha256": sha256_file(CALENDAR_MANIFEST_PATH),
                     "calendar_version": manifest.get("calendar_version"),
                     "span": manifest.get("span"), "sessions": len(sessions),
                     "note": CALENDAR_NOTE,
                     "gap_scope": "sessions in [first_bar, last_bar] clipped to the calendar span; "
                                  "bars outside the span are not gap-checked"},
        "output_files": [CSV_NAME, RUN_JSON_NAME],
        "no_judgements": "No threshold, STALE rule or score applied; B2 remains BLOCKED.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols-csv", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, default=None, help="File holding UPSTOX_ACCESS_TOKEN; if omitted, the process environment is used (no cwd .env).")
    args = parser.parse_args(argv)

    for name in (CSV_NAME, RUN_JSON_NAME):
        if (OUTPUT_DIR / name).exists():
            print(f"Error: {OUTPUT_DIR / name} already exists; outputs are new files only")
            return 1
    try:
        selection = load_selection(args.symbols_csv)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    sessions = load_sessions(CALENDAR_PATH)
    try:
        provider = UpstoxProvider(load_token(args.env_file))
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    started = datetime.now(timezone.utc)
    today = datetime.now(IST).date()
    rows, results, aborted = check_symbols(provider, selection, sessions, today, RateLimiter(REQUESTS_PER_SECOND))
    meta = build_meta(started=started, finished=datetime.now(timezone.utc), today=today, selection=selection,
                      rows=rows, results=results, aborted=aborted, symbols_csv=args.symbols_csv, sessions=sessions)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_outputs(OUTPUT_DIR, rows, meta)
    print(f"rows={meta['rows']} unique_keys={meta['unique_keys']} status_counts={meta['status_counts_unique_keys']}"
          + (f" ABORTED: {aborted}" if aborted else ""))
    return 2 if aborted else 0


if __name__ == "__main__":
    sys.exit(main())

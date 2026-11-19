"""Live intraday PAPER board (NOT VALIDATED) - run on your PC on market days. No orders.

    python scripts/equity_paper_board.py           # runs the day, exits after 15:31 IST
    python scripts/equity_paper_board.py --once    # one cycle now, then exit (testing)

Before 09:00: fetches NSE announcements since the previous session and lists
order-win fade alerts (frozen order-win rules, see equity_intel/paper_board/logic.py).
From 09:16, every 5 minutes: Upstox quotes for liquid NIFTY 500 stocks -> volume
surges; each fade alert becomes a paper short at the official open. At 15:31:
paper covers at the last price; the next run re-marks them with the official
close from data/daily_live. Writes data/paper_board/<date>.json (read by the
dashboard) and data/paper_board/trades.csv. Read-only on NSE and Upstox.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import time as _time
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from announcement_coverage_fetch import NSE_API, nse_session  # noqa: E402
from config.settings import Settings  # noqa: E402
from equity_intel.announcements import event_study as es  # noqa: E402
from equity_intel.config import IST  # noqa: E402
from equity_intel.paper_board import daily_update as du  # noqa: E402
from equity_intel.paper_board import logic as pb  # noqa: E402

DAILY = ROOT / "data" / "daily_live"
OUT = ROOT / "data" / "paper_board"
TRADES = OUT / "trades.csv"
SHARES = ROOT / "research" / "announcements" / "order_wins" / "shares_mcap17112026" / "shares.csv"
QUOTE_URL = "https://api.upstox.com/v2/market-quote/quotes"
INDEX = "NIFTY500_INDEX"
POLL_SECONDS = 300
FADE_FINAL, FIRST_QUOTES, CLOSE_MARK = time(9, 0), time(9, 16), time(15, 31)
HOLIDAY_CHECK = time(9, 30)
TRADE_FIELDS = ["date", "symbol", "amt_cr", "materiality", "status", "entry_open", "high", "low",
                "exit_price", "exit_source", "gross_pct", "net_pct", "reason"]
EQ_TYPES = {"EQ", "BE", "SM", "ST", "BZ"}


def load_daily() -> dict:
    out = {}
    for p in DAILY.glob("*.csv"):
        df = pd.read_csv(p)
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"]).dt.date
        out[p.stem] = df.drop_duplicates("date", keep="last").set_index("date")[["o", "h", "l", "c", "v"]].astype(float)
    return out


def load_shares() -> dict:
    with open(SHARES, encoding="utf-8") as f:
        return {r["symbol"]: (int(r["issued_size"] or 0), r["series"]) for r in csv.DictReader(f)}


def instrument_keys() -> dict:
    newest = sorted((ROOT / "data" / "reference").glob("upstox_NSE_instruments_*.json.gz"))[-1]
    return {r["trading_symbol"]: r["instrument_key"] for r in json.load(gzip.open(newest))
            if r.get("segment") == "NSE_EQ" and r.get("instrument_type") in EQ_TYPES}


def read_trades() -> list[dict]:
    if not TRADES.exists():
        return []
    with open(TRADES, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_trades(rows: list[dict]) -> None:
    tmp = TRADES.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in TRADE_FIELDS} for r in rows)
    os.replace(tmp, TRADES)


def reconcile(trades: list[dict], daily: dict) -> int:
    """Re-mark earlier paper trades with the official daily open/high/low/close."""
    n = 0
    for t in trades:
        if t.get("exit_source") == "official_close" or t.get("status") not in ("WAITING_OPEN", "OPEN", "CLOSED"):
            continue
        px, d = daily.get(t["symbol"]), date.fromisoformat(t["date"])
        if px is None or d not in px.index:
            continue
        o, h, l, c = (float(px.loc[d, k]) for k in ("o", "h", "l", "c"))
        t.update(pb.short_result(o, h, l, c), entry_open=o, high=h, low=l, exit_price=c,
                 exit_source="official_close")
        t.setdefault("reason", "")
        n += 1
    return n


def fetch_announcements(prev: date, today: date, folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    s = nse_session()
    resp = s.get(NSE_API, params={"index": "equities", "from_date": prev.strftime("%d-%m-%Y"),
                                  "to_date": today.strftime("%d-%m-%Y")}, timeout=60)
    resp.raise_for_status()
    (folder / f"NSE_ALL_{prev}_{today}_{datetime.now(IST):%H%M%S}.json").write_bytes(resp.content)
    return es.load_announcements(folder)


def fetch_quotes(token: str, keys: list[str], key_to_symbol: dict) -> dict:
    out = {}
    for i in range(0, len(keys), 500):
        resp = requests.get(QUOTE_URL, params={"instrument_key": ",".join(keys[i:i + 500])},
                            headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                            timeout=30)
        resp.raise_for_status()
        out.update(pb.parse_upstox_quotes(resp.json(), key_to_symbol))
    return out


def write_state(state: dict, today: date) -> None:
    path = OUT / f"{today}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="one cycle now, then exit")
    a = ap.parse_args(argv)
    now = datetime.now(IST)
    today = now.date()
    if today.weekday() >= 5:
        print("Weekend: no session.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    daily = load_daily()
    if INDEX not in daily:
        raise SystemExit(f"{DAILY / (INDEX + '.csv')} missing: run the daily refresh first")
    sessions, inferred = du.session_calendar(list(daily[INDEX].index), today)
    prev, data_asof = sessions[-2], max(d for d in daily[INDEX].index if d < today)
    shares, keys = load_shares(), instrument_keys()
    key_to_symbol = {v: k for k, v in keys.items()}
    trades = read_trades()
    if reconcile(trades, daily):
        write_trades(trades)
    base = pb.baselines({s: p for s, p in daily.items() if s != INDEX}, today, sessions)
    liquid = sorted(s for s, (_, val) in base.items() if val >= pb.SURGE_MIN_VALUE_CR and s in keys)
    settings = Settings()
    token = settings.UPSTOX_ANALYTICS_TOKEN or settings.UPSTOX_ACCESS_TOKEN
    state = {"date": today, "mode": "PAPER - NOT VALIDATED - no orders", "data_asof": data_asof,
             "prices_stale": data_asof < prev, "fade": {"alerts": [], "considered": [], "final": False},
             "surges": [], "surges_asof": None, "liquid_watched": len(liquid), "errors": [],
             "notes": [] if token else ["No Upstox token: set UPSTOX_ANALYTICS_TOKEN in .env (or run scripts/upstox_auth.py); quotes disabled."]}
    if state["prices_stale"]:
        state["notes"].append(f"Daily prices end {data_asof}; previous session {prev} is missing. Run "
                              "scripts/equity_daily_live_update.py - stocks without the previous close get no fade alert.")

    def err(where, exc):
        state["errors"] = (state["errors"] + [f"{datetime.now(IST):%H:%M:%S} {where}: {type(exc).__name__}: {str(exc)[:160]}"])[-10:]

    while True:
        now = datetime.now(IST)
        if not state["fade"]["final"]:
            try:
                ann = fetch_announcements(prev, today, OUT / str(today) / "announcements")
                recent = {t["symbol"]: date.fromisoformat(t["date"]) for t in trades
                          if t.get("status") in ("WAITING_OPEN", "OPEN", "CLOSED") and t["date"] < str(today)}
                alerts, considered = pb.fade_candidates(ann, today, sessions, daily, shares, recent)
                state["fade"] = {"alerts": alerts, "considered": considered, "final": now.time() >= FADE_FINAL,
                                 "asof": now.strftime("%H:%M:%S"), "announcements": len(ann)}
                if state["fade"]["final"]:
                    have = {(t["date"], t["symbol"]) for t in trades}
                    for al in alerts:
                        if (str(today), al["symbol"]) not in have:
                            trades.append({"date": str(today), "symbol": al["symbol"], "amt_cr": al["amt_cr"],
                                           "materiality": al["materiality"], "status": "WAITING_OPEN"})
                    write_trades(trades)
            except Exception as exc:  # recorded, never hidden
                err("announcements", exc)
        if token and now.time() >= FIRST_QUOTES:
            try:
                today_trades = [t for t in trades if t["date"] == str(today)]
                syms = sorted(set(liquid) | {t["symbol"] for t in today_trades})
                quotes = fetch_quotes(token, [keys[s] for s in syms if s in keys], key_to_symbol)
                quotes = {s: q for s, q in quotes.items() if q.get("last_trade_date") == today}
                if not quotes and now.time() >= HOLIDAY_CHECK:
                    state["notes"].append("No stock has traded today by 09:30: market closed (holiday?). "
                                          "Board stopped; today's fade alerts are void.")
                    for t in today_trades:
                        if t["status"] in ("WAITING_OPEN", "OPEN"):
                            t.update(status="VOID", reason="market closed today")
                    write_trades(trades)
                    state["trades_today"] = today_trades
                    state["updated"] = datetime.now(IST).strftime("%H:%M:%S")
                    write_state(state, today)
                    return 0
                state["surges"] = pb.surges(quotes, base, now.replace(tzinfo=None))
                state["surges_asof"] = now.strftime("%H:%M:%S")
                for t in today_trades:
                    q = quotes.get(t["symbol"])
                    if not q:
                        continue
                    if t["status"] == "WAITING_OPEN" and q["open"] > 0:
                        t.update(status="OPEN", entry_open=q["open"])
                    if t["status"] == "OPEN":
                        o = float(t["entry_open"])
                        t["live_net_pct"] = round(((o - q["ltp"]) / o - pb.COST) * 100, 3)
                        if now.time() >= CLOSE_MARK:
                            t.update(pb.short_result(o, q["high"], q["low"], q["ltp"]), high=q["high"],
                                     low=q["low"], exit_price=q["ltp"], exit_source="last_price_1531")
                write_trades(trades)
            except Exception as exc:
                err("quotes", exc)
        state["trades_today"] = [t for t in trades if t["date"] == str(today)]
        state["scorecard"] = pb.scorecard(trades)
        state["updated"] = datetime.now(IST).strftime("%H:%M:%S")
        write_state(state, today)
        print(f"{state['updated']} fade alerts {len(state['fade']['alerts'])} "
              f"(final {state['fade']['final']}), surges {len(state['surges'])}, errors {len(state['errors'])}")
        if a.once or now.time() >= CLOSE_MARK:
            return 0
        nxt = now + timedelta(seconds=60 if now.time() < FIRST_QUOTES else POLL_SECONDS)
        _time.sleep(max(5, (nxt - datetime.now(IST)).total_seconds()))


if __name__ == "__main__":
    sys.exit(main())

"""Smoke test of scripts/equity_paper_board.py with fake NSE/Upstox fetches and a fake clock (tmp dirs only)."""
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import equity_paper_board as run  # noqa: E402
from equity_intel.config import IST  # noqa: E402

TODAY = date(2026, 11, 19)
TEXT = "KEC International Limited has informed the Exchange that it has secured new orders of Rs 1,200 crore"


def _days(n=30):
    out, d = [], TODAY - timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


@pytest.fixture
def env(tmp_path, monkeypatch):
    daily = tmp_path / "daily_live"
    daily.mkdir()
    for sym, c, v in [("NIFTY500_INDEX", 23800, 0), ("KEC", 300.0, 1_000_000), ("BEL", 400.0, 30_000_000)]:
        pd.DataFrame({"date": _days(), "o": c, "h": c, "l": c, "c": c, "v": v}).to_csv(daily / f"{sym}.csv", index=False)
    shares = tmp_path / "shares.csv"
    shares.write_text("symbol,issued_size,series,source_sha256\nKEC,266200000,EQ,x\nBEL,7309778829,EQ,x\n")
    out = tmp_path / "paper_board"
    monkeypatch.setattr(run, "DAILY", daily)
    monkeypatch.setattr(run, "OUT", out)
    monkeypatch.setattr(run, "TRADES", out / "trades.csv")
    monkeypatch.setattr(run, "SHARES", shares)
    monkeypatch.setattr(run, "instrument_keys", lambda: {"KEC": "NSE_EQ|K", "BEL": "NSE_EQ|B"})
    monkeypatch.setattr(run.Settings, "UPSTOX_ACCESS_TOKEN", "tok", raising=False)

    def fake_ann(prev, today, folder):
        return pd.DataFrame([{"symbol": "KEC", "category": "Updates", "an_dt": datetime(2026, 11, 18, 19, 0),
                              "exchdisstime": datetime(2026, 11, 18, 19, 0), "event_ts": datetime(2026, 11, 18, 19, 0),
                              "ts_source": "exchdisstime", "attachment": None, "text": TEXT, "raw_file": "x"}])
    monkeypatch.setattr(run, "fetch_announcements", fake_ann)
    quotes = {"KEC": {"ltp": 296.0, "volume": 900_000, "open": 302.0, "high": 303.0, "low": 295.0, "prev_close": 300.0},
              "BEL": {"ltp": 401.0, "volume": 40_000_000, "open": 400.0, "high": 402.0, "low": 399.0, "prev_close": 400.0}}
    monkeypatch.setattr(run, "fetch_quotes", lambda token, keys, k2s: quotes)
    return out


def _at(monkeypatch, hh, mm):
    class Fake(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 19, hh, mm, tzinfo=IST)
    monkeypatch.setattr(run, "datetime", Fake)


def test_a_day_alert_then_open_then_close(env, monkeypatch):
    _at(monkeypatch, 9, 5)
    assert run.main(["--once"]) == 0
    st = json.loads((env / "2026-11-19.json").read_text())
    assert st["fade"]["final"] and [a["symbol"] for a in st["fade"]["alerts"]] == ["KEC"]
    assert st["trades_today"][0]["status"] == "WAITING_OPEN" and st["surges"] == []

    _at(monkeypatch, 10, 0)
    run.main(["--once"])
    st = json.loads((env / "2026-11-19.json").read_text())
    t = st["trades_today"][0]
    assert t["status"] == "OPEN" and float(t["entry_open"]) == 302.0
    assert t["live_net_pct"] == pytest.approx(((302 - 296) / 302 - 0.005) * 100, abs=1e-3)
    # 10:00 = 45 of 375 minutes (0.12): BEL 40M / (30M x 0.12) = 11.1x, KEC 0.9M / (1M x 0.12) = 7.5x
    assert [(s["symbol"], s["ratio"]) for s in st["surges"]] == [("BEL", 11.11), ("KEC", 7.5)]

    _at(monkeypatch, 15, 35)
    run.main(["--once"])
    rows = list(csv.DictReader(open(env / "trades.csv")))
    assert len(rows) == 1 and rows[0]["status"] == "CLOSED" and rows[0]["exit_source"] == "last_price_1531"
    assert float(rows[0]["net_pct"]) == pytest.approx(((302 - 296) / 302 - 0.005) * 100, abs=1e-3)
    assert json.loads((env / "2026-11-19.json").read_text())["scorecard"]["trades"] == 1


def test_weekend_does_nothing(env, monkeypatch):
    class Sat(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 21, 10, 0, tzinfo=IST)
    monkeypatch.setattr(run, "datetime", Sat)
    assert run.main(["--once"]) == 0 and not env.exists()


def test_next_morning_remarks_trades_with_the_official_daily_bar(env, monkeypatch):
    _at(monkeypatch, 9, 5)
    run.main(["--once"])                                   # alert, WAITING_OPEN (as if no token later)
    d = pd.read_csv(run.DAILY / "KEC.csv")
    d.loc[len(d)] = ["2026-11-19", 302.0, 304.0, 294.0, 297.0, 1e6]
    d.to_csv(run.DAILY / "KEC.csv", index=False)

    class Next(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, 8, 50, tzinfo=IST)
    monkeypatch.setattr(run, "datetime", Next)
    run.main(["--once"])
    t = [r for r in csv.DictReader(open(env / "trades.csv")) if r["date"] == "2026-11-19"][0]
    assert t["status"] == "CLOSED" and t["exit_source"] == "official_close"
    assert float(t["net_pct"]) == pytest.approx(((302 - 297) / 302 - 0.005) * 100, abs=1e-3)

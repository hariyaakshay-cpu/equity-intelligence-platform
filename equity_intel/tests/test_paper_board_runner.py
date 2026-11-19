"""Smoke test of scripts/equity_paper_board.py with fake NSE/Upstox/Telegram calls and a fake clock (tmp dirs only)."""
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
def messages(monkeypatch):
    """Telegram on with a fake sender in every runner test: nothing reaches the network or your phone."""
    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(run.telegram_v0, "send", lambda text, **kw: sent.append(text) or {"ok": True})
    return sent


@pytest.fixture
def env(tmp_path, monkeypatch, messages):
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
    quotes = {"KEC": {"ltp": 296.0, "volume": 900_000, "open": 302.0, "high": 303.0, "low": 295.0, "prev_close": 300.0,
                      "last_trade_date": TODAY},
              "BEL": {"ltp": 401.0, "volume": 40_000_000, "open": 400.0, "high": 402.0, "low": 399.0, "prev_close": 400.0,
                      "last_trade_date": TODAY}}
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


def test_holiday_no_trades_today_voids_the_alert_and_stops(env, monkeypatch, messages):
    stale = {"KEC": {"ltp": 296.0, "volume": 900_000, "open": 302.0, "high": 303.0, "low": 295.0, "prev_close": 300.0,
                     "last_trade_date": date(2026, 11, 18)}}
    monkeypatch.setattr(run, "fetch_quotes", lambda token, keys, k2s: stale)
    _at(monkeypatch, 9, 5)
    run.main(["--once"])
    _at(monkeypatch, 9, 20)
    run.main(["--once"])                                     # before 09:30: just waits, no fill from stale quotes
    assert json.loads((env / "2026-11-19.json").read_text())["trades_today"][0]["status"] == "WAITING_OPEN"
    _at(monkeypatch, 9, 35)
    run.main(["--once"])
    st = json.loads((env / "2026-11-19.json").read_text())
    assert st["trades_today"][0]["status"] == "VOID" and "holiday" in st["notes"][-1]
    assert st["surges"] == []
    assert sum("market closed (holiday?)" in m for m in messages) == 1


def test_stale_daily_prices_are_flagged_and_block_fade_alerts(env, monkeypatch):
    for f in run.DAILY.glob("*.csv"):                      # drop the last session (18 Nov) from every file
        d = pd.read_csv(f)
        d.iloc[:-1].to_csv(f, index=False)
    _at(monkeypatch, 9, 5)
    run.main(["--once"])
    st = json.loads((env / "2026-11-19.json").read_text())
    assert st["prices_stale"] and st["data_asof"] == "2026-11-17" and "previous session 2026-11-18" in st["notes"][0]
    assert st["fade"]["alerts"] == [] and st["fade"]["considered"][0]["reason"] == "no close for the previous session"


def _kinds(messages):
    return [m.splitlines()[1].split(" ")[0] for m in messages]      # line 2 = the message type


def test_telegram_sends_each_event_once(env, monkeypatch, messages):
    _at(monkeypatch, 9, 5)
    run.main(["--once"])                                     # start message + KEC fade alert
    _at(monkeypatch, 10, 0)
    run.main(["--once"])                                     # BEL and KEC surge
    run.main(["--once"])                                     # same minute again: nothing new
    _at(monkeypatch, 15, 35)
    run.main(["--once"])                                     # day summary
    assert _kinds(messages) == ["Board", "FADE", "New", "Day"]
    assert all(m.startswith("PAPER - NOT VALIDATED") for m in messages)
    assert "KEC: order Rs 1,200 cr" in messages[1]
    assert "BEL: 11.1x" in messages[2] and "KEC: 7.5x" in messages[2]
    assert "Fade KEC: net +1.49%" in messages[3]
    sent = json.loads((env / "2026-11-19.sent.json").read_text())
    assert sent["start"] and sent["fade"] and sent["summary"] and sent["surges"] == ["BEL", "KEC"]


def test_a_failed_send_is_recorded_once_retried_and_never_stops_the_board(env, monkeypatch, messages):
    def down(text, **kw):
        raise OSError("network down")
    monkeypatch.setattr(run.telegram_v0, "send", down)
    _at(monkeypatch, 9, 5)
    assert run.main(["--once"]) == 0
    st = json.loads((env / "2026-11-19.json").read_text())
    assert [e.split(" ", 1)[1] for e in st["errors"]] == ["telegram: OSError: network down"]
    assert not json.loads((env / "2026-11-19.sent.json").read_text())["start"]
    monkeypatch.setattr(run.telegram_v0, "send", lambda text, **kw: messages.append(text) or {"ok": True})
    _at(monkeypatch, 9, 10)
    run.main(["--once"])
    assert _kinds(messages) == ["Board", "FADE"]             # retried, not lost


def test_a_repeating_board_error_is_sent_once(env, monkeypatch, messages):
    def broken(prev, today, folder):
        raise ConnectionError("NSE reset")
    monkeypatch.setattr(run, "fetch_announcements", broken)
    _at(monkeypatch, 9, 5)
    run.main(["--once"])
    _at(monkeypatch, 9, 10)
    run.main(["--once"])
    warnings = [m for m in messages if "Board warning" in m]
    assert len(warnings) == 1 and "announcements: ConnectionError: NSE reset" in warnings[0]


def test_telegram_test_flag(env, monkeypatch, messages):
    assert run.main(["--telegram-test"]) == 0
    assert len(messages) == 1 and "Test message" in messages[0]
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    assert run.main(["--telegram-test"]) == 1 and len(messages) == 1

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from equity_intel.paper_board import logic as pb
from equity_intel.paper_board import surge as sv


def _at(h, m):
    return datetime(2026, 11, 20, h, m)


def _rows(*items):                                        # (symbol, ratio, last price, previous close)
    surges = [{"symbol": s, "ratio": r, "ltp": l, "change_pct": round((l / p - 1) * 100, 2)} for s, r, l, p in items]
    return surges, {s: {"ltp": l, "prev_close": p} for s, r, l, p in items}


def _closed(day, symbol, net):
    return {"date": day, "symbol": symbol, "status": "CLOSED", "gross_pct": net + 0.18, "net_pct": net}


def _sample(n_days=60, per_day=5):
    out = []
    for d in range(n_days):
        day = (date(2027, 1, 1) + timedelta(days=d)).isoformat()
        out += [_closed(day, f"S{d * per_day + k:03d}", 0.2 + 0.1 * ((d + k) % 3)) for k in range(per_day)]
    return out


def test_frozen_document_and_constants_are_intact():
    ok, msg = sv.rule_intact()
    assert ok, msg


def test_a_changed_document_or_constant_stops_scoring(tmp_path, monkeypatch):
    edited = tmp_path / "edited.md"
    edited.write_bytes(sv.PREREG_DOC.read_bytes() + b"\nedited\n")
    assert sv.rule_intact(doc=edited)[0] is False
    crlf = tmp_path / "crlf.md"                           # line endings alone are not a change
    crlf.write_bytes(sv.PREREG_DOC.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert sv.rule_intact(doc=crlf)[0] is True
    monkeypatch.setattr(pb, "SURGE_TOP", 10)
    ok, msg = sv.rule_intact()
    assert not ok and "SURGE_TOP" in msg


def test_triggers_take_up_movers_by_ratio_then_symbol_capped_at_five():
    surges, quotes = _rows(("AAA", 9.0, 101, 100), ("BBB", 12.0, 99, 100), ("CCC", 9.0, 102, 100),
                           ("DDD", 3.0, 105, 100), ("EEE", 2.0, 101, 100), ("FFF", 1.8, 110, 100),
                           ("GGG", 1.6, 100, 100))
    new = sv.new_triggers([], surges, quotes, _at(9, 31))
    assert [t["symbol"] for t in new] == ["AAA", "CCC", "DDD", "EEE", "FFF"]     # BBB down, GGG flat
    assert all(t["status"] == "WAITING_ENTRY" and t["trigger_at"] == "2026-11-20T09:31:00" for t in new)
    voids = [{"symbol": f"V{i}", "status": "VOID"} for i in range(4)]            # VOID trades keep their slots
    assert [t["symbol"] for t in sv.new_triggers(voids, surges, quotes, _at(9, 31))] == ["AAA"]
    held = [{"symbol": "AAA", "status": "OPEN"}]                                  # one trade per stock a session
    assert "AAA" not in [t["symbol"] for t in sv.new_triggers(held, surges, quotes, _at(9, 36))]


def test_no_trigger_outside_0930_to_1300():
    surges, quotes = _rows(("AAA", 9.0, 101, 100))
    assert sv.new_triggers([], surges, quotes, _at(9, 29)) == []
    assert sv.new_triggers([], surges, quotes, _at(13, 1)) == []
    assert len(sv.new_triggers([], surges, quotes, _at(13, 0))) == 1


def test_entry_fills_at_the_next_check_or_voids_after_15_minutes():
    surges, quotes = _rows(("AAA", 9.0, 101, 100), ("BBB", 8.0, 50, 49))
    trades = sv.step([], surges, quotes, _at(9, 31))
    assert [t["status"] for t in trades] == ["WAITING_ENTRY", "WAITING_ENTRY"]    # never filled in the trigger check
    assert sv.step(trades, surges, {"AAA": {"ltp": 101.5, "prev_close": 100}}, _at(9, 36)) == []
    assert trades[0]["status"] == "OPEN" and trades[0]["entry_price"] == 101.5
    assert trades[0]["entry_at"] == "2026-11-20T09:36:00" and trades[1]["status"] == "WAITING_ENTRY"
    sv.step(trades, surges, {"BBB": {"ltp": 51, "prev_close": 49}}, _at(9, 47))  # 16 minutes after the trigger
    assert trades[1]["status"] == "VOID" and trades[1]["reason"] == sv.VOID_NO_ENTRY


def test_exit_at_the_first_check_from_1515_with_018_cost():
    t = {"date": "2026-11-20", "symbol": "AAA", "status": "OPEN", "entry_price": 100.0}
    quotes = {"AAA": {"ltp": 101.0, "prev_close": 99}}
    sv.step([t], [], quotes, _at(15, 10))
    assert t["status"] == "OPEN"
    sv.step([t], [], quotes, _at(15, 16))
    assert t["status"] == "CLOSED" and t["exit_source"] == "last_price_1515"
    assert t["gross_pct"] == pytest.approx(1.0) and t["net_pct"] == pytest.approx(0.82)


def test_next_morning_open_trade_takes_the_official_close_and_waiting_is_void():
    trades = [{"date": "2026-11-20", "symbol": "AAA", "status": "OPEN", "entry_price": 100.0},
              {"date": "2026-11-20", "symbol": "BBB", "status": "WAITING_ENTRY"},
              {"date": "2026-11-23", "symbol": "CCC", "status": "OPEN", "entry_price": 10.0}]
    daily = {"AAA": pd.DataFrame({"c": [99.0]}, index=[date(2026, 11, 20)])}
    assert sv.reconcile(trades, daily, date(2026, 11, 23)) == 2
    assert trades[0]["status"] == "CLOSED" and trades[0]["exit_source"] == "official_close"
    assert trades[0]["net_pct"] == pytest.approx(-1.18)
    assert trades[1]["status"] == "VOID" and trades[2]["status"] == "OPEN"        # today's trade untouched


def test_drawdown_is_peak_to_trough_of_daily_net_sums():
    trades = [_closed("2026-11-20", "A", 2.0), _closed("2026-11-23", "B", -5.0), _closed("2026-11-24", "C", -1.0),
              _closed("2026-11-24", "D", -2.0), _closed("2026-11-25", "E", 4.0)]
    assert sv.max_drawdown(trades) == pytest.approx(8.0)                          # cum 2, -3, -6, -2


def test_review_waits_for_r1_but_stops_early_on_drawdown():
    assert sv.review([_closed("2026-11-20", "A", 0.5), _closed("2026-11-23", "B", -0.2)], {})["verdict"] == "NOT_YET"
    crash = [_closed(f"2026-12-{d:02d}", f"S{d}", -5.0) for d in range(1, 7)]   # 30 points down, 6 trades
    r = sv.review(crash, {})
    assert r["verdict"] == "FAIL" and r["reason"].startswith("R3")


def test_review_pass_then_fail_on_one_stock_making_the_profit():
    trades = _sample()
    sectors = {t["symbol"]: f"SEC{i % 10}" for i, t in enumerate(trades)}
    r = sv.review(trades, sectors, resamples=500)
    assert r["trades"] == 300 and r["sessions"] == 60 and r["verdict"] == "PASS", r
    trades[0]["net_pct"] = 200.0
    r = sv.review(trades, sectors, resamples=500)
    assert r["verdict"] == "FAIL" and not r["checks"]["symbol_share_ok"]


def test_bootstrap_is_reproducible_with_the_frozen_seed():
    trades = _sample(n_days=20)
    assert sv.bootstrap_ci(trades, 300) == sv.bootstrap_ci(trades, 300)
    lo, hi = sv.bootstrap_ci(trades, 300)
    assert lo <= 0.3 <= hi

from datetime import datetime, timedelta, timezone

from equity_intel.intraday import backtest as bt
from equity_intel.intraday.setups import Bar, orb_long, pdh_break_long, vwap_reclaim_long

IST = timezone(timedelta(hours=5, minutes=30))


def session(closes, day=(2026, 10, 20), vol=1000, spread=0.5):
    start = datetime(*day, 9, 15, tzinfo=IST)
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(Bar(start + timedelta(minutes=5 * i), o, max(o, c) + spread, min(o, c) - spread, c, vol))
    return out


def test_orb_triggers_on_first_close_above_range():
    bars = session([100, 101, 100.5, 100.2, 103, 104])
    assert orb_long(bars) == 4


def test_orb_not_after_window_end():
    flat = [100, 101, 100.5] + [100.2] * 30 + [110]
    assert orb_long(session(flat)) is None


def test_orb_gap_in_grid_blocks_trigger():
    bars = session([100, 101, 100.5, 100.2, 103])
    del bars[3]
    assert orb_long(bars) is None


def test_orb_zero_volume_opening_blocks():
    bars = session([100, 101, 100.5, 105])
    bars[1] = Bar(bars[1].ts, 100, 101.5, 100, 101, 0)
    assert orb_long(bars) is None


def test_pdh_break():
    bars = session([100] * 5 + [106])
    assert pdh_break_long(bars, prev_high=105) == 5
    assert pdh_break_long(bars, prev_high=None) is None


def test_vwap_reclaim_requires_prev_close_and_min_bar():
    closes = [100] * 8 + [97, 97, 97, 97, 97, 101]  # dip below vwap, then reclaim at index 13
    bars = session(closes)
    assert vwap_reclaim_long(bars, prev_close=99) == 13
    assert vwap_reclaim_long(bars, prev_close=102) is None


def test_cost_is_positive_and_sane():
    c = bt.round_trip_cost_pct()
    assert 0.05 < c < 0.5


def test_run_setup_caps_five_per_day_and_orders_by_time_then_symbol():
    day = "2026-10-20"
    closes = [100, 101, 100.5, 100.2, 103] + [104] * 70
    sessions = {s: {day: session(closes)} for s in "ABCDEFG"}
    trades = bt.run_setup("ORB_LONG", sessions)
    assert len(trades) == 5
    assert [t["symbol"] for t in trades] == list("ABCDE")


def test_evaluate_fails_when_too_few_trades():
    r = bt.evaluate([{"date": "2026-10-20", "symbol": "A", "net_pct": 1.0}] * 3)
    assert r["verdict"] == "FAIL" and not r["checks"]["min_trades"]

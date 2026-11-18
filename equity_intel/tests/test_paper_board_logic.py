from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from equity_intel.paper_board import logic as pb

WIN_TEXT = "KEC International Limited has informed the Exchange that it has secured new orders of Rs 1,200 crore"


def _sessions(n=25, end=date(2026, 11, 19)):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _daily(sessions, close=300.0, vol=1_000_000):
    return pd.DataFrame({"o": close, "h": close, "l": close, "c": close, "v": float(vol)},
                        index=sessions[:-1])


def _ann(rows):
    return pd.DataFrame([{"symbol": s, "category": "Updates", "an_dt": ts, "exchdisstime": ts,
                          "event_ts": ts, "ts_source": "exchdisstime", "attachment": None,
                          "text": t, "raw_file": "x"} for s, ts, t in rows])


S = _sessions()
TODAY = S[-1]
SHARES = {"KEC": (266_200_000, "EQ"), "BEX": (266_200_000, "BE")}


def test_order_win_overnight_becomes_a_fade_alert_with_materiality():
    ann = _ann([("KEC", datetime(2026, 11, 18, 19, 5), WIN_TEXT)])
    alerts, considered = pb.fade_candidates(ann, TODAY, S, {"KEC": _daily(S)}, SHARES, {})
    assert [a["symbol"] for a in alerts] == ["KEC"]
    a = alerts[0]
    assert a["mcap_cr"] == pytest.approx(266_200_000 * 300 / 1e7, rel=1e-6)
    assert a["materiality"] == pytest.approx(1200 / a["mcap_cr"], abs=1e-4)
    assert considered[0]["kept"] and considered[0]["reason"].startswith("ALERT")


def test_entry_session_rule_today_before_0900_counts_after_0900_does_not():
    early = _ann([("KEC", datetime(2026, 11, 19, 8, 30), WIN_TEXT)])
    late = _ann([("KEC", datetime(2026, 11, 19, 10, 0), WIN_TEXT)])
    assert pb.fade_candidates(early, TODAY, S, {"KEC": _daily(S)}, SHARES, {})[0]
    assert pb.fade_candidates(late, TODAY, S, {"KEC": _daily(S)}, SHARES, {}) == ([], [])


def test_largest_amount_per_symbol_is_used():
    ann = _ann([("KEC", datetime(2026, 11, 18, 18, 0), WIN_TEXT),
                ("KEC", datetime(2026, 11, 18, 18, 5), WIN_TEXT.replace("1,200", "2,400"))])
    alerts, _ = pb.fade_candidates(ann, TODAY, S, {"KEC": _daily(S)}, SHARES, {})
    assert alerts[0]["amt_cr"] == 2400


@pytest.mark.parametrize("case,reason", [
    ("small", "< 5%"), ("illiquid", "illiquid"), ("be", "not EQ"), ("noshares", "no share count"),
    ("noprices", "no daily prices"), ("recent", "within 20 sessions")])
def test_every_dropped_order_win_is_listed_with_its_reason(case, reason):
    sym, text, daily, recent = "KEC", WIN_TEXT, {"KEC": _daily(S)}, {}
    if case == "small":
        text = WIN_TEXT.replace("1,200", "20")
    elif case == "illiquid":
        daily = {"KEC": _daily(S, close=10.0, vol=1000)}
    elif case == "be":
        sym, daily = "BEX", {"BEX": _daily(S)}
    elif case == "noshares":
        sym, daily = "ZZZ", {"ZZZ": _daily(S)}
    elif case == "noprices":
        daily = {}
    elif case == "recent":
        recent = {"KEC": S[-5]}
    ann = _ann([(sym, datetime(2026, 11, 18, 19, 0), text.replace("KEC International", sym))])
    alerts, considered = pb.fade_candidates(ann, TODAY, S, daily, SHARES, recent)
    assert alerts == [] and not considered[0]["kept"] and reason in considered[0]["reason"]


def test_non_order_win_text_is_ignored():
    ann = _ann([("KEC", datetime(2026, 11, 18, 19, 0), "Outcome of board meeting; GST demand order of Rs 50 crore")])
    assert pb.fade_candidates(ann, TODAY, S, {"KEC": _daily(S)}, SHARES, {}) == ([], [])


def test_short_result_and_void_cases():
    r = pb.short_result(100, 101, 97, 98)
    assert r["status"] == "CLOSED" and r["gross_pct"] == pytest.approx(2.0) and r["net_pct"] == pytest.approx(1.5)
    assert pb.short_result(100, 103, 99, 103)["net_pct"] == pytest.approx(-3.5)
    assert pb.short_result(90, 95, 90, 90)["status"] == "VOID"
    assert pb.short_result(110, 110, 105, 110)["status"] == "VOID"


def test_surge_ratio_scales_by_elapsed_session():
    base = {"AAA": (1_000_000, 50.0), "TINY": (1_000_000, 2.0)}
    noon = datetime(2026, 11, 19, 12, 22, 30)          # 187.5 of 375 minutes = half the session
    q = {"AAA": {"ltp": 105, "volume": 1_000_000, "prev_close": 100},
         "TINY": {"ltp": 10, "volume": 9_000_000, "prev_close": 10}}
    rows = pb.surges(q, base, noon)
    assert [r["symbol"] for r in rows] == ["AAA"] and rows[0]["ratio"] == pytest.approx(2.0)
    assert rows[0]["change_pct"] == pytest.approx(5.0)
    assert pb.surges(q, base, datetime(2026, 11, 19, 9, 25)) == []      # before 09:30
    q["AAA"]["volume"] = 600_000
    assert pb.surges(q, base, noon) == []                                 # 1.2x < 1.5x


def test_baselines_need_15_of_20_prior_rows():
    d = _daily(S)
    assert pb.baselines({"KEC": d}, TODAY, S)["KEC"] == (1_000_000.0, pytest.approx(30.0))
    assert "KEC" not in pb.baselines({"KEC": d.iloc[-10:]}, TODAY, S)


def test_scorecard_counts_closed_trades_only():
    trades = [{"date": "2026-11-19", "status": "CLOSED", "net_pct": 1.5},
              {"date": "2026-11-20", "status": "CLOSED", "net_pct": -0.5},
              {"date": "2026-11-21", "status": "OPEN", "net_pct": None},
              {"date": "2026-11-22", "status": "VOID", "net_pct": None}]
    sc = pb.scorecard(trades)
    assert sc["trades"] == 2 and sc["wins"] == 1 and sc["avg_net_pct"] == pytest.approx(0.5)
    assert pb.scorecard([]) == {"trades": 0}


def test_parse_upstox_quotes_maps_by_instrument_token():
    payload = {"status": "success", "data": {
        "NSE_EQ:KEC": {"instrument_token": "NSE_EQ|INE389H01022", "last_price": 314.85, "volume": 812345,
                       "net_change": -4.15, "ohlc": {"open": 318.0, "high": 319.5, "low": 312.1, "close": 314.85},
                       "last_trade_time": "1794995998260"},
        "NSE_EQ:XYZ": {"instrument_token": "NSE_EQ|UNKNOWN", "last_price": 1.0},
        "NSE_EQ:BAD": {"instrument_token": "NSE_EQ|INE000000000", "last_price": "n/a"}}}
    q = pb.parse_upstox_quotes(payload, {"NSE_EQ|INE389H01022": "KEC", "NSE_EQ|INE000000000": "BAD"})
    assert list(q) == ["KEC"]
    assert q["KEC"] == {"ltp": 314.85, "volume": 812345, "open": 318.0, "high": 319.5, "low": 312.1,
                        "prev_close": pytest.approx(319.0), "last_trade_date": date(2026, 11, 18)}

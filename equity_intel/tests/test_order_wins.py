from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from equity_intel.announcements import order_wins as ow


def _sessions(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _px(sessions, o=100.0, c=101.0, v=1_000_000.0):
    return pd.DataFrame({"o": o, "h": max(o, c) + 1, "l": min(o, c) - 1, "c": c, "v": v},
                        index=pd.Index(sessions))


@pytest.mark.parametrize("text,amt", [
    ('Bharat Electronics (BEL) receives Orders worth Rs.5900 Crore', 5900.0),
    ("Tejas Networks wins Rs. 696 crore order from BSNL", 696.0),
    ("Latteys Industries has informed regarding 'Work Order Of Rs 2.06 Cr' secured", 2.06),
    ("Company bagged a contract of INR 1,250.50 crores", 1250.5),
    ("Received purchase order worth Rs 450 lakhs", 4.5),
    ("Awarded LOA of ₹ 88 cr from NHAI", 88.0),
])
def test_order_win_positive(text, amt):
    assert ow.is_order_win(text)
    assert ow.parse_amount_cr(text) == pytest.approx(amt)


@pytest.mark.parametrize("text", [
    "Order issued by the Additional Commissioner of GST, demand of Rs 12 crore",   # NEG
    "Receipt of tax assessment order of Rs 5 crore",                               # NEG
    "Company receives order worth USD 10 million",                                 # no INR amount
    "Board approved fund raise of Rs 500 crore",                                   # no ORDER/WIN
    "Order book stands at Rs 4,000 crore",                                         # no WIN word
    "",
])
def test_order_win_negative(text):
    assert not ow.is_order_win(text)


def test_build_units_largest_amount_and_non_overlap():
    s = _sessions(date(2015, 1, 5), 80)
    ev = lambda k, h=19: datetime.combine(s[k], datetime.min.time()) + timedelta(hours=h)
    wins = pd.DataFrame([
        {"symbol": "A", "event_ts": ev(10), "amt_cr": 50.0, "ts_source": "an_dt"},
        {"symbol": "A", "event_ts": ev(10, 20), "amt_cr": 80.0, "ts_source": "an_dt"},  # same entry, larger
        {"symbol": "A", "event_ts": ev(25), "amt_cr": 30.0, "ts_source": "an_dt"},      # entry s[26]: 15 after s[11] -> overlap
        {"symbol": "A", "event_ts": ev(40), "amt_cr": 30.0, "ts_source": "an_dt"},      # entry s[41]: 30 after -> kept
        {"symbol": "B", "event_ts": ev(25), "amt_cr": 10.0, "ts_source": "an_dt"},
    ])
    u, drops = ow.build_units(wins, s)
    assert list(zip(u.symbol, u.entry, u.amt_cr)) == [("A", s[11], 80.0), ("A", s[41], 30.0),
                                                       ("B", s[26], 10.0)]
    assert drops == {"overlap": 1}


def test_build_observations_materiality_returns_and_drops():
    s = _sessions(date(2016, 1, 4), 70)
    idx = _px(s, o=1000.0, c=1005.0)
    universe = {"U1": _px(s, o=100.0, c=101.0, v=2e6), "U2": _px(s, o=100.0, c=103.0, v=2e6)}
    bench = ow.EqualWeightBenchmark(universe, s)
    stock = _px(s, o=50.0, c=55.0, v=1e6)                  # value 5.5 cr/day > 2 cr
    units = pd.DataFrame([{"symbol": "X", "entry": s[30], "amt_cr": 11.0, "ts_source": "exchdisstime"},
                          {"symbol": "NOSH", "entry": s[30], "amt_cr": 1.0, "ts_source": "an_dt"},
                          {"symbol": "THIN", "entry": s[30], "amt_cr": 1.0, "ts_source": "an_dt"}])
    prices = {"X": stock, "NOSH": stock, "THIN": _px(s, v=10.0)}
    shares = {"X": 20_000_000, "THIN": 1_000_000}          # X mcap = 2e7*55/1e7 = 110 cr
    obs, drops = ow.build_observations(units, prices, idx, bench, shares, s)
    assert drops == {"no_shares": 1, "illiquid": 1}
    h5 = obs[obs.horizon == "H5"].iloc[0]
    assert h5["mcap_cr"] == pytest.approx(110.0)
    assert h5["materiality"] == pytest.approx(0.10)
    assert h5["raw"] == pytest.approx(0.10)                 # 55/50 - 1
    assert h5["abn"] == pytest.approx(0.10 - 0.02)          # ew of U1 (+1%) and U2 (+3%)
    assert h5["net_abn"] == pytest.approx(0.10 - 0.02 - 0.005)
    assert h5["net_abn_index"] == pytest.approx(0.10 - 0.005 - 0.005)
    assert h5["period"] == "dev"
    assert sorted(obs.horizon) == ["H0", "H20", "H5"]


def _obs(n, value, mat=0.06, n_symbols=60, hz="H5"):
    s = _sessions(date(2016, 1, 4), n)
    return pd.DataFrame({"symbol": [f"S{i % n_symbols}" for i in range(n)], "entry": s,
                         "exit": s, "horizon": hz, "amt_cr": 1.0, "mcap_cr": 10.0,
                         "materiality": mat, "raw": value, "abn": value, "abn_index": value,
                         "net_raw": value, "net_abn": value, "net_abn_index": value,
                         "ts_source": "an_dt", "big_move": False, "period": "dev"})


def test_evaluate_primary_verdicts_and_secondary_info():
    res = ow.evaluate(_obs(300, 0.01), "dev", ["H5"])
    prim = res[res.role == "PRIMARY"].iloc[0]
    assert prim["verdict"] == "PASS" and prim["confidence"] == pytest.approx(1 - 0.05 / 3)
    assert set(res[res.role == "secondary"]["verdict"]) == {"INFO"}
    assert ow.evaluate(_obs(299, 0.01), "dev", ["H5"]).iloc[0]["verdict"] == "INSUFFICIENT_DATA"
    small = ow.evaluate(_obs(400, 0.01, mat=0.03), "dev", ["H5"])
    assert small.iloc[0]["n"] == 0 and small.iloc[0]["verdict"] == "INSUFFICIENT_DATA"
    assert ow.evaluate(_obs(300, -0.01), "dev", ["H5"]).iloc[0]["verdict"] == "FAIL"
    assert ow.evaluate(_obs(300, 0.01, n_symbols=5), "dev", ["H5"]).iloc[0]["verdict"] == "FAIL"

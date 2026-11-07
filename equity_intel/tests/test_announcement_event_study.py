import json
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from equity_intel.announcements import event_study as es


def _sessions(start: date, n: int, skip=()):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5 and d not in skip:
            out.append(d)
        d += timedelta(days=1)
    return out


def _px(sessions, o=100.0, c=101.0, v=2_000_000.0, h=None, l=None):
    return pd.DataFrame({"o": o, "h": h if h is not None else max(o, c) + 1,
                         "l": l if l is not None else min(o, c) - 1,
                         "c": c, "v": v}, index=pd.Index(sessions))


# ---- timestamps and entry rule -------------------------------------------

def test_parse_ts_handles_missing_and_bad():
    assert es.parse_ts("14-May-2021 19:41:20") == datetime(2021, 5, 14, 19, 41, 20)
    for bad in (None, "", "-", "None", "garbage"):
        assert es.parse_ts(bad) is None


def test_entry_session_rules():
    holiday = date(2024, 5, 20)                       # a Monday treated as holiday
    s = _sessions(date(2024, 5, 13), 10, skip=(holiday,))
    fri = date(2024, 5, 17)
    assert es.entry_session(datetime(2024, 5, 17, 8, 59), s) == fri       # before 09:00
    assert es.entry_session(datetime(2024, 5, 17, 9, 0), s) == date(2024, 5, 21)  # at 09:00 -> next (holiday skipped)
    assert es.entry_session(datetime(2024, 5, 17, 12, 0), s) == date(2024, 5, 21)  # market hours -> next
    assert es.entry_session(datetime(2024, 5, 17, 19, 0), s) == date(2024, 5, 21)  # after close -> next
    assert es.entry_session(datetime(2024, 5, 18, 10, 0), s) == date(2024, 5, 21)  # weekend
    assert es.entry_session(datetime(2030, 1, 1, 10, 0), s) is None


def test_period_of():
    assert es.period_of(date(2022, 6, 1)) == "dev"
    assert es.period_of(date(2025, 6, 1)) == "holdout"
    assert es.period_of(date(2020, 6, 1)) == "other"


# ---- loading ----------------------------------------------------------------

def test_load_announcements_prefers_dissemination_and_dedups(tmp_path):
    rec = {"symbol": "ABC", "desc": " Press Release ", "an_dt": "14-May-2021 19:41:13",
           "exchdisstime": "14-May-2021 19:41:20", "attchmntFile": "u1", "attchmntText": "t"}
    old = dict(rec, an_dt="10-May-2018 18:23:00", exchdisstime="-", attchmntFile="u2")
    bad = {"symbol": "", "desc": "X", "an_dt": "10-May-2018 18:23:00"}
    nots = {"symbol": "XYZ", "desc": "X", "an_dt": "-", "exchdisstime": "-"}
    (tmp_path / "NSE_ALL_2021-05-14.json").write_text(json.dumps([rec, old, bad, nots]))
    (tmp_path / "NSE_ALL_2021-05-15.json").write_text(json.dumps({"data": [rec]}))  # duplicate
    (tmp_path / "NSE_ALL_2021-05-16.json").write_text("<html>denied</html>")       # not JSON
    df = es.load_announcements(tmp_path)
    assert len(df) == 2
    new = df[df["attachment"] == "u1"].iloc[0]
    assert new["category"] == "Press Release"
    assert new["ts_source"] == "exchdisstime"
    assert new["event_ts"] == datetime(2021, 5, 14, 19, 41, 20)
    assert df[df["attachment"] == "u2"].iloc[0]["ts_source"] == "an_dt"


def test_load_prices_later_dir_wins(tmp_path):
    a, b = tmp_path / "early", tmp_path / "recent"
    a.mkdir(); b.mkdir()
    (a / "ABC.csv").write_text("date,o,h,l,c,v\n2021-09-30,1,1,1,1,1\n2021-10-01,2,2,2,2,2\n")
    (b / "ABC.csv").write_text("date,o,h,l,c,v\n2021-10-01,3,3,3,3,3\n2021-10-04,4,4,4,4,4\n")
    px = es.load_prices([a, b], "ABC")
    assert list(px.index) == [date(2021, 9, 30), date(2021, 10, 1), date(2021, 10, 4)]
    assert px.loc[date(2021, 10, 1), "o"] == 3
    assert es.load_prices([a, b], "NONE") is None


# ---- observations -----------------------------------------------------------

def _ann(rows):
    return pd.DataFrame([dict(attachment=None, text=None, raw_file="f", an_dt=r["event_ts"],
                              exchdisstime=r["event_ts"], ts_source="exchdisstime", **r)
                         for r in rows])


def test_build_observations_returns_and_dedup():
    s = _sessions(date(2022, 1, 3), 40)
    idx = _px(s, o=1000.0, c=1010.0)                   # index +1% open->close each day
    px = _px(s, o=100.0, c=103.0)                       # stock +3% open->close on any single day
    ev = datetime.combine(s[25], datetime.min.time()) + timedelta(hours=19)
    ann = _ann([{"symbol": "ABC", "category": "Results", "event_ts": ev},
                {"symbol": "ABC", "category": "Results", "event_ts": ev + timedelta(minutes=5)}])
    obs, drops = es.build_observations(ann, {"ABC": px}, idx, s)
    assert len(obs) == 3                                # one unit x 3 horizons
    h0 = obs[obs["horizon"] == "H0"].iloc[0]
    assert h0["entry"] == s[26] and h0["exit"] == s[26]
    assert h0["raw"] == pytest.approx(0.03)
    assert h0["abn"] == pytest.approx(0.02)
    assert h0["net_abn"] == pytest.approx(0.02 - 0.001824)
    h5 = obs[obs["horizon"] == "H5"].iloc[0]
    assert h5["exit"] == s[31]
    assert h5["net_raw"] == pytest.approx(0.03 - 0.0035)
    assert not drops


def test_build_observations_drops():
    s = _sessions(date(2022, 1, 3), 40)
    idx = _px(s)
    ev = datetime.combine(s[25], datetime.min.time()) + timedelta(hours=19)
    illiquid = _px(s, v=10.0)
    locked = _px(s, o=100.0, c=100.0, h=100.0, l=99.0)
    short_hist = _px(s[20:])                            # fewer than 15 prior rows
    ann = _ann([{"symbol": n, "category": "C", "event_ts": ev}
                for n in ("ILL", "LOCK", "SHORT", "NOFILE")]
               + [{"symbol": "ILL", "category": "C",
                   "event_ts": datetime(2030, 1, 1, 10)}])
    obs, drops = es.build_observations(
        ann, {"ILL": illiquid, "LOCK": locked, "SHORT": short_hist}, idx, s)
    assert obs.empty
    assert drops == {"illiquid": 2, "locked_entry": 1, "no_price_file": 1,
                     "no_entry_session": 1}


def test_build_observations_missing_exit_counted_per_horizon():
    s = _sessions(date(2022, 1, 3), 30)
    idx = _px(s)
    ev = datetime.combine(s[26], datetime.min.time()) + timedelta(hours=19)  # entry s[27]
    obs, drops = es.build_observations(
        _ann([{"symbol": "ABC", "category": "C", "event_ts": ev}]), {"ABC": _px(s)}, idx, s)
    assert sorted(obs["horizon"]) == ["H0", "H1"]
    assert drops == {"H5:no_exit_session": 1}


# ---- statistics -------------------------------------------------------------

def test_bootstrap_lower_constant_and_grouping():
    assert es.bootstrap_lower([0.01] * 50, range(50), 0.95) == pytest.approx(0.01)
    lb = es.bootstrap_lower([0.02, -0.01] * 100, range(200), 0.95)
    assert lb < 0.005


def test_max_symbol_share():
    df = pd.DataFrame({"symbol": ["A", "B", "B"], "net_abn": [0.03, 0.005, 0.005]})
    assert es.max_symbol_share(df) == pytest.approx(0.75)
    assert pd.isna(es.max_symbol_share(pd.DataFrame({"symbol": ["A"], "net_abn": [-0.1]})))


def _obs(n, value, period="dev", n_symbols=50, cat="C", hz="H0"):
    s = _sessions(date(2022, 1, 3) if period == "dev" else date(2025, 1, 6), n)
    return pd.DataFrame({"symbol": [f"S{i % n_symbols}" for i in range(n)], "category": cat,
                         "entry": s, "exit": s, "horizon": hz, "raw": value + 0.01,
                         "abn": value + 0.002, "net_raw": value, "net_abn": value,
                         "ts_source": "exchdisstime", "big_move": False, "period": period})


def test_evaluate_dev_rules():
    good = es.evaluate(_obs(300, 0.004), [("C", "H0")], "dev", 30).iloc[0]
    assert good["verdict"] == "PASS" and good["confidence"] == pytest.approx(1 - 0.05 / 30)
    assert es.evaluate(_obs(299, 0.004), [("C", "H0")], "dev", 30).iloc[0]["verdict"] == "FAIL"
    assert es.evaluate(_obs(300, -0.004), [("C", "H0")], "dev", 30).iloc[0]["verdict"] == "FAIL"
    concentrated = es.evaluate(_obs(300, 0.004, n_symbols=5), [("C", "H0")], "dev", 30)
    assert concentrated.iloc[0]["verdict"] == "FAIL"


def test_evaluate_holdout_rules_and_eligibility():
    assert es.evaluate(_obs(100, 0.004, "holdout"), [("C", "H0")], "holdout", 30).iloc[0]["verdict"] == "PASS"
    assert es.evaluate(_obs(99, 0.004, "holdout"), [("C", "H0")], "holdout", 30).iloc[0]["verdict"] == "FAIL"
    both = pd.concat([_obs(300, 0.0, cat="Big"), _obs(299, 0.0, cat="Small"),
                      _obs(300, 0.0, cat="OnlyH1", hz="H1")])
    assert es.eligible_categories(both) == ["Big"]

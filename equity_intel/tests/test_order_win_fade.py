from datetime import date, timedelta

import pandas as pd
import pytest

from equity_intel.announcements import order_win_fade as f


def _px(o=100.0, h=102.0, l=98.0, c=99.0, day=date(2024, 3, 4)):
    return pd.DataFrame({"o": [o], "h": [h], "l": [l], "c": [c], "v": [1e6]}, index=[day])


def _obs(**kw):
    row = {"symbol": "AAA", "entry": date(2024, 3, 4), "horizon": "H0", "materiality": 0.06,
           "amt_cr": 60.0, "mcap_cr": 1000.0, "raw": -0.01, "abn": -0.008,
           "big_move": False, "ts_source": "exchdisstime"}
    row.update(kw)
    return pd.DataFrame([row])


def test_short_returns_are_minus_long_returns_less_cost():
    d, drops = f.fade_observations(_obs(), {"AAA": _px()}, {"AAA": "EQ"})
    r = d.iloc[0]
    assert r.short_raw == pytest.approx(0.01) and r.short_abn == pytest.approx(0.008)
    assert r.net_short_raw == pytest.approx(0.005) and r.net_short_abn == pytest.approx(0.003)
    assert not drops


@pytest.mark.parametrize("kw", [{"horizon": "H5"}, {"materiality": 0.049},
                                {"entry": date(2022, 12, 30)}, {"entry": date(2026, 11, 2)}])
def test_rows_outside_the_frozen_sample_are_excluded(kw):
    px = _px(day=kw.get("entry", date(2024, 3, 4)))
    d, _ = f.fade_observations(_obs(**kw), {"AAA": px}, {"AAA": "EQ"})
    assert d.empty


def test_non_eq_series_and_locked_low_entry_are_dropped_and_counted():
    d, drops = f.fade_observations(_obs(), {"AAA": _px()}, {"AAA": "BE"})
    assert d.empty and drops["not_eq_series"] == 1
    d, drops = f.fade_observations(_obs(), {"AAA": _px(o=90, h=95, l=90, c=90)}, {"AAA": "EQ"})
    assert d.empty and drops["locked_low_entry"] == 1
    d, drops = f.fade_observations(_obs(), {"AAA": _px()}, {})
    assert d.empty and drops["not_eq_series"] == 1


def _sample(n, sessions, net_abn, net_raw, symbols=50):
    days = [date(2023, 1, 2) + timedelta(days=i) for i in range(sessions)]
    return pd.DataFrame({"symbol": [f"S{i % symbols}" for i in range(n)],
                         "entry": [days[i % sessions] for i in range(n)],
                         "net_short_abn": [net_abn + (0.001 if i % 2 else -0.001) for i in range(n)],
                         "net_short_raw": [net_raw] * n, "big_move": [False] * n})


def test_pass_requires_every_rule():
    assert f.evaluate_fade(_sample(150, 60, 0.01, 0.01))["verdict"] == "PASS"
    assert f.evaluate_fade(_sample(150, 60, 0.01, -0.001))["verdict"] == "FAIL"     # raw not > 0
    assert f.evaluate_fade(_sample(150, 60, -0.01, 0.01))["verdict"] == "FAIL"      # abnormal not > 0
    assert f.evaluate_fade(_sample(150, 60, 0.01, 0.01, symbols=5))["verdict"] == "FAIL"  # one symbol > 10%


def test_too_few_trades_or_sessions_is_insufficient_data():
    assert f.evaluate_fade(_sample(99, 60, 0.01, 0.01))["verdict"] == "INSUFFICIENT_DATA"
    assert f.evaluate_fade(_sample(150, 39, 0.01, 0.01))["verdict"] == "INSUFFICIENT_DATA"
    assert f.evaluate_fade(pd.DataFrame())["verdict"] == "INSUFFICIENT_DATA"


def test_frozen_constants_match_the_preregistration():
    assert f.PERIOD == (date(2023, 1, 1), date(2026, 10, 31)) and f.THRESHOLD == 0.05
    assert f.COST == 0.005 and f.MIN_N == 100 and f.MIN_SESSIONS == 40
    assert f.MAX_SYMBOL_SHARE == 0.10 and f.CONFIDENCE == 0.95 and f.SEED == 20261118 and f.N_BOOT == 10_000

"""PROVISIONAL v0 scorers: band edges and None-handling."""
import pytest

from equity_intel.contracts.features import FeatureSet
from equity_intel.scoring import components_v0 as c


def fs(**kw):
    return FeatureSet(instrument_id="X", **kw)


@pytest.mark.parametrize("rsi,pts", [(39.9, 0), (40, 2), (49.9, 2), (50, 4), (55, 6), (60, 8), (69.9, 8), (70, 10), (100, 10)])
def test_rsi_edges(rsi, pts):
    assert c.momentum(fs(rsi=rsi, roc=-5)).score == pts  # roc<=0 -> 0


@pytest.mark.parametrize("roc,pts", [(-3, 0), (0, 0), (0.01, 2), (2, 4), (4, 6), (6, 8), (9.9, 8), (10, 10)])
def test_roc_edges(roc, pts):
    assert c.momentum(fs(rsi=30, roc=roc)).score == pts  # rsi<40 -> 0


def test_momentum_sums_both_parts_and_max_is_20():
    assert c.momentum(fs(rsi=80, roc=12)).score == 20


@pytest.mark.parametrize("kw", [dict(rsi=50), dict(roc=3), dict()])
def test_momentum_none_if_either_missing_never_zero(kw):
    assert c.momentum(fs(**kw)).score is None


@pytest.mark.parametrize("rp,pts", [(-9, 0), (-5, 4), (-2, 8), (0, 12), (3, 16), (6, 20), (25, 20)])
def test_relative_strength_edges(rp, pts):
    assert c.relative_strength(fs(relative_return=rp)).score == pts


@pytest.mark.parametrize("rv,pts", [(0.5, 0), (0.8, 4), (1.0, 8), (1.5, 12), (2.0, 16), (3.0, 20), (9, 20)])
def test_volume_edges(rv, pts):
    assert c.volume(fs(relative_volume=rv)).score == pts


def test_rs_and_volume_none_when_missing():
    assert c.relative_strength(fs()).score is None
    assert c.volume(fs()).score is None


@pytest.mark.parametrize("d,pts", [(0, 12), (1.99, 12), (2, 9), (5, 6), (10, 3), (19.9, 3), (20, 0), (60, 0)])
def test_structure_distance_edges(d, pts):
    assert c.structure_distance_points(fs(w52_complete=True, distance_from_high=d)) == pts


@pytest.mark.parametrize("kw", [dict(w52_complete=False, distance_from_high=1), dict(w52_complete=None, distance_from_high=1), dict(w52_complete=True)])
def test_structure_distance_none_without_complete_window(kw):
    assert c.structure_distance_points(fs(**kw)) is None


# ---- Trend, Structure (breakout) and composite -------------------------------
FULL = dict(close=110.0, ema_short=105.0, ema_medium=100.0, ema_long=90.0, ema_medium_lag=95.0,
            w52_complete=True, distance_from_high=1.0, prior_high_short=108.0, prior_high_medium=109.0,
            rsi=75, roc=12, relative_return=7, relative_volume=3.5)


def test_trend_all_five_tests_pass_is_20():
    assert c.trend(fs(**FULL)).score == 20


def test_trend_counts_each_failed_test_as_minus_4():
    f = dict(FULL, close=102.0)  # still above E20? no: 102 < 105 -> fails test 1; above E50 ok
    assert c.trend(fs(**f)).score == 16


def test_trend_none_without_ema200_or_lag():
    assert c.trend(fs(**dict(FULL, ema_long=None))).score is None
    assert c.trend(fs(**dict(FULL, ema_medium_lag=None))).score is None


@pytest.mark.parametrize("close,pts", [(110, 8), (108.5, 4), (108, 0), (100, 0)])
def test_breakout_points(close, pts):
    assert c.structure_breakout_points(fs(**dict(FULL, close=close))) == pts


def test_structure_is_distance_plus_breakout_and_none_without_w52():
    assert c.structure(fs(**FULL)).score == 12 + 8
    assert c.structure(fs(**dict(FULL, w52_complete=False))).score is None


def test_composite_is_exact_sum_when_all_five_present():
    r = c.score_instrument(fs(**FULL))
    assert [x.score for x in r.components] == [20, 20, 20, 20, 20]
    assert r.composite == 100


def test_composite_none_if_any_component_none_no_partial_sum():
    r = c.score_instrument(fs(**dict(FULL, relative_return=None)))
    assert r.composite is None
    assert any(x.score is None for x in r.components)


def test_horizon_scores_are_percent_of_their_own_max_and_none_without_parts():
    h = c.horizon_scores(fs(**FULL))
    assert h == {"short": 100, "medium": 100}
    # momentum 0 (rsi<40, roc<=0) leaves volume 20 + breakout 8 of 48 -> 58
    low = c.horizon_scores(fs(**dict(FULL, rsi=30, roc=-1)))
    assert low["short"] == int(100 * 28 / 48 + 0.5) and low["medium"] == 100
    # no partial sum: missing volume kills SHORT only, missing relative return kills MEDIUM only
    assert c.horizon_scores(fs(**dict(FULL, relative_volume=None))) == {"short": None, "medium": 100}
    assert c.horizon_scores(fs(**dict(FULL, relative_return=None))) == {"short": 100, "medium": None}

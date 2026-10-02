"""Pure indicator functions: deterministic, no band/score applied."""
import math

import pytest

from equity_intel.indicators.context import atr_percent, average_true_range
from equity_intel.indicators.momentum import rate_of_change, relative_strength_index
from equity_intel.indicators.relative import relative_return
from equity_intel.indicators.structure import distance_from_high, rolling_high
from equity_intel.indicators.trend import exponential_moving_average
from equity_intel.indicators.volume import relative_volume


def _closes(n, start=100.0, step=0.5):
    return [start + step * i for i in range(n)]


def test_ema_requires_explicit_period_and_returns_none_when_insufficient():
    assert exponential_moving_average(_closes(10), period=20) is None


def test_ema_is_deterministic():
    closes = _closes(30)
    a = exponential_moving_average(closes, period=20)
    b = exponential_moving_average(closes, period=20)
    assert a == b
    assert a[-1] is not None


def test_ema_rejects_non_positive_period():
    try:
        exponential_moving_average(_closes(10), period=0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_rsi_returns_none_below_minimum_history():
    assert relative_strength_index(_closes(5), period=14) is None


def test_rsi_is_bounded_0_100():
    closes = [100, 102, 101, 105, 103, 108, 110, 107, 111, 115, 112, 118, 120, 119, 121]
    value = relative_strength_index(closes, period=14)
    assert value is not None
    assert 0.0 <= value <= 100.0


def test_roc_returns_none_when_insufficient_history():
    assert rate_of_change(_closes(5), lookback=10) is None


def test_roc_is_deterministic_percent_change():
    closes = [100.0] * 10 + [110.0]
    value = rate_of_change(closes, lookback=10)
    assert value == pytest.approx(10.0)


def test_rolling_high_excludes_current_when_asked():
    values = [1.0, 2.0, 3.0, 100.0]
    assert rolling_high(values, window=3, exclude_current=True) == 3.0
    assert rolling_high(values, window=3, exclude_current=False) == 100.0


def test_distance_from_high_handles_non_positive_high():
    assert distance_from_high(current=10.0, high=0.0) is None
    assert distance_from_high(current=90.0, high=100.0) == 10.0


def test_relative_return_does_not_assume_a_benchmark_source():
    value = relative_return(instrument_start=100.0, instrument_end=110.0, benchmark_start=100.0, benchmark_end=105.0)
    assert value == pytest.approx(5.0)


def test_relative_volume_never_defaults_missing_to_zero():
    assert relative_volume(current_volume=None, prior_volumes=[1.0, 2.0]) is None
    assert relative_volume(current_volume=10.0, prior_volumes=[1.0, None]) is None
    assert relative_volume(current_volume=10.0, prior_volumes=[]) is None


def test_relative_volume_computes_ratio_excluding_current_bar():
    value = relative_volume(current_volume=20.0, prior_volumes=[10.0, 10.0])
    assert value == 2.0


def test_atr_is_context_only_and_returns_none_below_minimum_history():
    highs = [1.0, 2.0]
    lows = [0.5, 1.0]
    closes = [0.8, 1.5]
    assert average_true_range(highs, lows, closes, period=14) is None


def test_atr_percent_handles_zero_close():
    assert atr_percent(atr_value=1.0, close=0.0) is None
    assert atr_percent(atr_value=1.0, close=10.0) == 10.0

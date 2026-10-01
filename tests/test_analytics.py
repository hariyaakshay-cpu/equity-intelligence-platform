"""Tests for price analytics."""

from datetime import date, timedelta

import pandas as pd
import pytest

from services.analytics import compute_indicators, rsi


def series(values):
    start = date(2025, 1, 1)
    return pd.Series(values, index=[start + timedelta(days=i) for i in range(len(values))])


def test_empty():
    assert compute_indicators(pd.Series(dtype=float)) == {"observations": 0}


def test_short_history_gives_none():
    r = compute_indicators(series([100, 101, 102]))
    assert r["sma_20"] is None and r["rsi_14"] is None and r["returns"]["1w"] is None
    assert r["close"] == 102.0


def test_linear_uptrend():
    r = compute_indicators(series(range(100, 400)))
    assert r["sma_20"] == pytest.approx(389.5)  # mean of 380..399
    assert r["returns"]["1w"] == pytest.approx(399 / 394 - 1, abs=1e-4)
    assert r["rsi_14"] == 100.0
    assert r["pct_from_52w_high"] == 0.0
    assert r["high_52w"] == 399.0 and r["low_52w"] == 148.0


def test_rsi_bounds_and_downtrend():
    assert rsi(series(range(400, 100, -1))).iloc[-1] == pytest.approx(0, abs=1e-6)
    noisy = series([100 + (i % 7) - (i % 3) for i in range(100)])
    assert 0 <= rsi(noisy).iloc[-1] <= 100

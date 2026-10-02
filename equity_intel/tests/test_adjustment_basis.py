"""Tests for equity_intel.scanner.adjustment_check. Pure data, no network, no DB."""
from datetime import date

import pytest

from equity_intel.scanner.adjustment_check import compare_across_event

EX = date(2026, 3, 9)  # a Monday


def test_adjusted_series_is_near_one():
    closes = [(date(2026, 3, 5), 100.0), (date(2026, 3, 6), 101.0), (date(2026, 3, 9), 100.5)]
    r = compare_across_event(closes, EX, 2)
    assert r.conclusive
    assert (r.date_before, r.date_on_or_after) == (date(2026, 3, 6), date(2026, 3, 9))
    assert r.observed_ratio == pytest.approx(100.5 / 101.0)
    assert r.distance_to_adjusted < r.distance_to_unadjusted


def test_unadjusted_series_is_near_one_over_divisor():
    closes = [(date(2026, 3, 6), 200.0), (date(2026, 3, 9), 101.0)]
    r = compare_across_event(closes, EX, 2)
    assert r.unadjusted_expected_ratio == 0.5
    assert r.observed_ratio == pytest.approx(0.505)
    assert r.distance_to_unadjusted < r.distance_to_adjusted


def test_ex_date_on_weekend_uses_next_session():
    closes = [(date(2026, 3, 6), 100.0), (date(2026, 3, 9), 99.0)]
    r = compare_across_event(closes, date(2026, 3, 7), 2)  # Saturday
    assert (r.date_before, r.date_on_or_after) == (date(2026, 3, 6), date(2026, 3, 9))


def test_input_order_does_not_matter():
    closes = [(date(2026, 3, 9), 99.0), (date(2026, 3, 6), 100.0)]
    assert compare_across_event(closes, EX, 2).close_before == 100.0


def test_no_session_before_is_inconclusive():
    r = compare_across_event([(date(2026, 3, 9), 99.0)], EX, 2)
    assert not r.conclusive and r.observed_ratio is None and r.close_before is None


def test_no_session_on_or_after_is_inconclusive():
    r = compare_across_event([(date(2026, 3, 6), 100.0)], EX, 2)
    assert not r.conclusive and r.observed_ratio is None and r.close_on_or_after is None


def test_empty_series_is_inconclusive():
    assert not compare_across_event([], EX, 2).conclusive


@pytest.mark.parametrize("divisor", [1, 0.5, 0, -2])
def test_divisor_must_exceed_one(divisor):
    with pytest.raises(ValueError):
        compare_across_event([(date(2026, 3, 6), 100.0)], EX, divisor)


def test_non_positive_close_rejected():
    with pytest.raises(ValueError):
        compare_across_event([(date(2026, 3, 6), 0.0), (date(2026, 3, 9), 99.0)], EX, 2)

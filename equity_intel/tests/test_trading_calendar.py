"""Tests for equity_intel.scanner.trading_calendar.

No network: benchmark_candles are always a plain list of fakes with a
.timestamp attribute, never a real HistoricalCandle fetched from Upstox.
"""
from datetime import datetime

import pytest

from equity_intel.scanner.acquisition import AuthFailedError
from equity_intel.scanner.trading_calendar import (
    BENCHMARK_INSTRUMENT_KEY,
    CALENDAR_VERIFICATION_UNVERIFIED_INDEX_ONLY,
    CalendarInvalidError,
    build_trading_calendar,
    fetch_and_build_calendar,
)


class _FakeCandle:
    def __init__(self, timestamp):
        self.timestamp = timestamp


def _candles(*dates):
    return [_FakeCandle(datetime(*d)) for d in dates]


def test_builds_calendar_from_candle_dates():
    candles = _candles((2026, 9, 21), (2026, 9, 22), (2026, 9, 25))
    result = build_trading_calendar(candles, now=datetime(2026, 9, 26, 10, 0))
    assert result.calendar_dates == ["2026-09-21", "2026-09-22", "2026-09-25"]
    assert result.calendar_verification == CALENDAR_VERIFICATION_UNVERIFIED_INDEX_ONLY


def test_latest_closed_session_excludes_today_before_cutoff():
    candles = _candles((2026, 9, 25), (2026, 9, 28))
    result = build_trading_calendar(candles, now=datetime(2026, 9, 28, 10, 0))
    assert result.latest_closed_session == "2026-09-25"


def test_latest_closed_session_includes_today_after_cutoff():
    candles = _candles((2026, 9, 25), (2026, 9, 28))
    result = build_trading_calendar(candles, now=datetime(2026, 9, 28, 19, 0))
    assert result.latest_closed_session == "2026-09-28"


def test_latest_closed_session_excludes_a_future_date():
    candles = _candles((2026, 9, 25), (2026, 9, 29))  # 2026-09-29 is in the future relative to "now"
    result = build_trading_calendar(candles, now=datetime(2026, 9, 28, 19, 0))
    assert result.latest_closed_session == "2026-09-25"


def test_raises_calendar_invalid_for_empty_candle_list():
    with pytest.raises(CalendarInvalidError):
        build_trading_calendar([], now=datetime(2026, 9, 28, 10, 0))


def test_raises_calendar_invalid_when_no_session_date_is_closed_yet():
    candles = _candles((2026, 9, 29),)  # only a future date
    with pytest.raises(CalendarInvalidError):
        build_trading_calendar(candles, now=datetime(2026, 9, 28, 10, 0))


def test_raises_calendar_invalid_for_a_candle_missing_a_timestamp():
    class _NoTimestamp:
        timestamp = None

    with pytest.raises(CalendarInvalidError):
        build_trading_calendar([_NoTimestamp()], now=datetime(2026, 9, 28, 10, 0))


def test_deduplicates_repeated_dates():
    candles = _candles((2026, 9, 25), (2026, 9, 25))
    result = build_trading_calendar(candles, now=datetime(2026, 9, 26, 10, 0))
    assert result.calendar_dates == ["2026-09-25"]


class _FakeProviderReturning:
    def __init__(self, candles=None, error=None, auth_fails=False):
        self._candles = candles or []
        self._error = error
        self._auth_fails = auth_fails

    def get_historical_data(self, symbol, interval, start_date, end_date):
        if self._auth_fails:
            from core.providers.upstox_provider import AuthenticationError

            raise AuthenticationError("bad token")
        if self._error:
            from core.providers.upstox_provider import ProviderAPIError

            raise ProviderAPIError(self._error)
        return self._candles


def test_fetch_and_build_calendar_uses_the_benchmark_instrument_key():
    seen = {}

    class _RecordingProvider(_FakeProviderReturning):
        def get_historical_data(self, symbol, interval, start_date, end_date):
            seen["symbol"] = symbol
            return super().get_historical_data(symbol, interval, start_date, end_date)

    provider = _RecordingProvider(candles=_candles((2026, 9, 25),))
    fetch_and_build_calendar(
        provider, start_date=datetime(2026, 1, 1), end_date=datetime(2026, 9, 26), now=datetime(2026, 9, 26, 10, 0)
    )
    assert seen["symbol"] == BENCHMARK_INSTRUMENT_KEY


def test_fetch_and_build_calendar_raises_calendar_invalid_on_provider_error():
    provider = _FakeProviderReturning(error="503 Service Unavailable")
    with pytest.raises(CalendarInvalidError):
        fetch_and_build_calendar(
            provider, start_date=datetime(2026, 1, 1), end_date=datetime(2026, 9, 26), now=datetime(2026, 9, 26, 10, 0)
        )


def test_fetch_and_build_calendar_raises_calendar_invalid_on_empty_response():
    provider = _FakeProviderReturning(candles=[])
    with pytest.raises(CalendarInvalidError):
        fetch_and_build_calendar(
            provider, start_date=datetime(2026, 1, 1), end_date=datetime(2026, 9, 26), now=datetime(2026, 9, 26, 10, 0)
        )


def test_fetch_and_build_calendar_lets_auth_failed_propagate_not_calendar_invalid():
    provider = _FakeProviderReturning(auth_fails=True)
    with pytest.raises(AuthFailedError):
        fetch_and_build_calendar(
            provider, start_date=datetime(2026, 1, 1), end_date=datetime(2026, 9, 26), now=datetime(2026, 9, 26, 10, 0)
        )

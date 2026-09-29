"""Tests for equity_intel.scanner.acquisition.

Every provider here is a small local fake -- no test touches the network
or imports requests/tenacity's real retry timing. RateLimiter tests use
tiny, explicit requests_per_second values so they run in well under a
second rather than actually waiting ~0.2s per call.
"""
import time

import pytest
from core.providers.upstox_provider import (
    AuthenticationError,
    InvalidSymbolError,
    ProviderAPIError,
    ProviderConnectionError,
)

from equity_intel.scanner.acquisition import (
    AuthFailedError,
    RateLimiter,
    fetch_symbol_candles,
    fetch_universe_candles,
)


class _FakeProvider:
    def __init__(self, *, candles=None, raises=None):
        self._candles = candles if candles is not None else []
        self._raises = raises
        self.calls = []

    def get_historical_data(self, symbol, interval, start_date, end_date):
        self.calls.append(symbol)
        if self._raises is not None:
            raise self._raises
        return self._candles


def test_fetch_symbol_candles_returns_candles_and_no_error_on_success():
    provider = _FakeProvider(candles=["c1", "c2"])
    candles, error = fetch_symbol_candles(provider, "NSE_EQ|INE1", None, None)
    assert candles == ["c1", "c2"]
    assert error is None


def test_fetch_symbol_candles_raises_auth_failed_on_401():
    provider = _FakeProvider(raises=AuthenticationError("invalid token"))
    with pytest.raises(AuthFailedError):
        fetch_symbol_candles(provider, "NSE_EQ|INE1", None, None)


def test_fetch_symbol_candles_returns_a_reason_for_a_provider_api_error():
    provider = _FakeProvider(raises=ProviderAPIError("500 - server error"))
    candles, error = fetch_symbol_candles(provider, "NSE_EQ|INE1", None, None)
    assert candles == []
    assert "500" in error


def test_fetch_symbol_candles_returns_a_reason_for_a_connection_error():
    provider = _FakeProvider(raises=ProviderConnectionError("timed out"))
    candles, error = fetch_symbol_candles(provider, "NSE_EQ|INE1", None, None)
    assert candles == []
    assert error is not None


def test_fetch_symbol_candles_returns_a_reason_for_an_invalid_symbol():
    provider = _FakeProvider(raises=InvalidSymbolError("bad symbol"))
    candles, error = fetch_symbol_candles(provider, "not-a-key", None, None)
    assert candles == []
    assert error is not None


def test_fetch_universe_candles_collects_one_result_per_symbol():
    provider = _FakeProvider(candles=["c1"])
    results = fetch_universe_candles(
        provider,
        {"AAA": "NSE_EQ|INE1", "BBB": "NSE_EQ|INE2"},
        None,
        None,
        rate_limiter=RateLimiter(requests_per_second=1000),
    )
    assert set(results.keys()) == {"AAA", "BBB"}
    assert results["AAA"] == (["c1"], None)
    assert provider.calls == ["NSE_EQ|INE1", "NSE_EQ|INE2"]


def test_fetch_universe_candles_one_bad_symbol_does_not_stop_the_rest():
    class _MixedProvider:
        def __init__(self):
            self.calls = []

        def get_historical_data(self, symbol, interval, start_date, end_date):
            self.calls.append(symbol)
            if symbol == "NSE_EQ|BAD":
                raise ProviderAPIError("404 - not found")
            return ["ok"]

    provider = _MixedProvider()
    results = fetch_universe_candles(
        provider,
        {"GOOD1": "NSE_EQ|OK1", "BAD": "NSE_EQ|BAD", "GOOD2": "NSE_EQ|OK2"},
        None,
        None,
        rate_limiter=RateLimiter(requests_per_second=1000),
    )
    assert results["GOOD1"] == (["ok"], None)
    assert results["GOOD2"] == (["ok"], None)
    assert results["BAD"][0] == []
    assert results["BAD"][1] is not None
    # All three symbols were attempted -- the bad one didn't abort the loop.
    assert set(provider.calls) == {"NSE_EQ|OK1", "NSE_EQ|BAD", "NSE_EQ|OK2"}


def test_fetch_universe_candles_propagates_auth_failed_and_stops():
    class _AuthFailProvider:
        def __init__(self):
            self.calls = []

        def get_historical_data(self, symbol, interval, start_date, end_date):
            self.calls.append(symbol)
            if symbol == "NSE_EQ|SECOND":
                raise AuthenticationError("token expired")
            return ["ok"]

    provider = _AuthFailProvider()
    with pytest.raises(AuthFailedError):
        fetch_universe_candles(
            provider,
            {"FIRST": "NSE_EQ|FIRST", "SECOND": "NSE_EQ|SECOND", "THIRD": "NSE_EQ|THIRD"},
            None,
            None,
            rate_limiter=RateLimiter(requests_per_second=1000),
        )
    # THIRD was never attempted -- the abort happened at SECOND.
    assert provider.calls == ["NSE_EQ|FIRST", "NSE_EQ|SECOND"]


def test_rate_limiter_does_not_sleep_on_the_first_call():
    limiter = RateLimiter(requests_per_second=1)
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start < 0.05


def test_rate_limiter_paces_consecutive_calls():
    limiter = RateLimiter(requests_per_second=20)  # 50ms interval
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04  # allow small scheduling slack under 50ms


def test_rate_limiter_does_not_over_sleep_when_calls_are_already_spaced_out():
    limiter = RateLimiter(requests_per_second=1000)  # 1ms interval
    limiter.wait()
    time.sleep(0.02)
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start < 0.01

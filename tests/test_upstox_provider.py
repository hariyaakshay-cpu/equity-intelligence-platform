from datetime import datetime, UTC
from unittest.mock import MagicMock

import pytest

from config import Settings
from core.providers.upstox_provider import InvalidSymbolError, UpstoxProvider


def test_provider_initializes_with_access_token() -> None:
    settings = Settings(UPSTOX_ACCESS_TOKEN="test-access-token")

    provider = UpstoxProvider(settings)

    assert provider.base_url == "https://api.upstox.com/v3"


def test_provider_raises_when_access_token_is_missing() -> None:
    settings = Settings(UPSTOX_ACCESS_TOKEN=None)

    with pytest.raises(
        ValueError,
        match="UPSTOX_ACCESS_TOKEN is required in settings to use UpstoxProvider",
    ):
        UpstoxProvider(settings)


def test_provider_session_uses_bearer_access_token() -> None:
    settings = Settings(UPSTOX_ACCESS_TOKEN="test-access-token")

    provider = UpstoxProvider(settings)

    assert provider.session.headers["Authorization"] == "Bearer test-access-token"
    assert provider.session.headers["Accept"] == "application/json"
    assert provider.session.headers["Content-Type"] == "application/json"


def _provider_with_mocked_session(candles=None):
    settings = Settings(UPSTOX_ACCESS_TOKEN="test-access-token")
    provider = UpstoxProvider(settings)
    captured = {}

    def fake_request(method, url, timeout=30, **kwargs):
        captured["method"] = method
        captured["url"] = url
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.raise_for_status = lambda: None
        response.json = lambda: {"status": "success", "data": {"candles": candles or []}}
        return response

    provider.session.request = fake_request
    return provider, captured


def test_get_historical_data_builds_the_exact_v3_url_for_an_equity_isin_key():
    provider, captured = _provider_with_mocked_session()

    provider.get_historical_data(
        "NSE_EQ|INE745G01043",
        "1day",
        datetime(2025, 8, 22, tzinfo=UTC),
        datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert captured["method"] == "GET"
    assert captured["url"] == (
        "https://api.upstox.com/v3/historical-candle/"
        "NSE_EQ%7CINE745G01043/days/1/2026-09-25/2025-08-22"
    )


def test_get_historical_data_builds_the_exact_v3_url_for_an_index_key_with_space():
    provider, captured = _provider_with_mocked_session()

    provider.get_historical_data(
        "NSE_INDEX|Nifty 500",
        "1day",
        datetime(2025, 8, 22, tzinfo=UTC),
        datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert captured["url"] == (
        "https://api.upstox.com/v3/historical-candle/"
        "NSE_INDEX%7CNifty%20500/days/1/2026-09-25/2025-08-22"
    )
    assert "%7C" in captured["url"]
    assert "%20" in captured["url"]


def test_get_historical_data_maps_5minute_to_minutes_unit_interval_5():
    provider, captured = _provider_with_mocked_session()

    provider.get_historical_data(
        "NSE_EQ|INE745G01043",
        "5minute",
        datetime(2025, 8, 22, tzinfo=UTC),
        datetime(2026, 9, 25, tzinfo=UTC),
    )

    assert "/minutes/5/" in captured["url"]


def test_get_historical_data_rejects_colon_delimited_symbol():
    provider, _ = _provider_with_mocked_session()

    with pytest.raises(InvalidSymbolError):
        provider.get_historical_data(
            "NSE:RELIANCE",
            "1day",
            datetime(2025, 8, 22, tzinfo=UTC),
            datetime(2026, 9, 25, tzinfo=UTC),
        )


def test_get_historical_data_rejects_symbol_without_pipe_segment():
    provider, _ = _provider_with_mocked_session()

    with pytest.raises(InvalidSymbolError):
        provider.get_historical_data(
            "RELIANCE",
            "1day",
            datetime(2025, 8, 22, tzinfo=UTC),
            datetime(2026, 9, 25, tzinfo=UTC),
        )


def test_get_historical_data_rejects_empty_identifier_after_pipe():
    provider, _ = _provider_with_mocked_session()

    with pytest.raises(InvalidSymbolError):
        provider.get_historical_data(
            "NSE_EQ|",
            "1day",
            datetime(2025, 8, 22, tzinfo=UTC),
            datetime(2026, 9, 25, tzinfo=UTC),
        )


def test_get_historical_data_parses_open_interest_when_present():
    candles = [["2025-01-02T00:00:00+05:30", 9.0, 10.0, 8.0, 9.5, 900, 42]]
    provider, _ = _provider_with_mocked_session(candles=candles)

    result = provider.get_historical_data(
        "NSE_EQ|INE745G01043",
        "1day",
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 3, tzinfo=UTC),
    )

    assert len(result) == 1
    assert result[0].open_interest == 42


def test_get_historical_data_leaves_open_interest_none_when_absent():
    candles = [["2025-01-03T00:00:00+05:30", 10.0, 11.0, 9.0, 10.5, 1000]]
    provider, _ = _provider_with_mocked_session(candles=candles)

    result = provider.get_historical_data(
        "NSE_EQ|INE745G01043",
        "1day",
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 3, tzinfo=UTC),
    )

    assert len(result) == 1
    assert result[0].open_interest is None


def test_get_historical_data_sorts_newest_first_input_to_oldest_first_output():
    candles = [
        ["2025-01-03T00:00:00+05:30", 10.0, 11.0, 9.0, 10.5, 1000],
        ["2025-01-01T00:00:00+05:30", 8.0, 9.0, 7.0, 8.5, 800],
        ["2025-01-02T00:00:00+05:30", 9.0, 10.0, 8.0, 9.5, 900],
    ]
    provider, _ = _provider_with_mocked_session(candles=candles)

    result = provider.get_historical_data(
        "NSE_EQ|INE745G01043",
        "1day",
        datetime(2025, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 3, tzinfo=UTC),
    )

    assert [c.timestamp for c in result] == sorted(c.timestamp for c in result)
    assert result[0].close == 8.5
    assert result[-1].close == 10.5

import pytest

from config import Settings
from core.providers.upstox_provider import UpstoxProvider


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

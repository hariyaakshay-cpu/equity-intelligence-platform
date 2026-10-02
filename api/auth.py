"""API-key authentication via the X-API-Key header."""

import hmac
from functools import lru_cache

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from config import Settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@lru_cache
def get_settings() -> Settings:
    """Cached settings; override in tests via app.dependency_overrides."""
    return Settings()


def require_api_key(
    key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Reject requests without a valid API key.

    Fails closed: if no keys are configured the API refuses all
    authenticated requests rather than running open.
    """
    valid = [k.strip() for k in settings.API_KEYS.split(",") if k.strip()]
    if not valid:
        raise HTTPException(status_code=503, detail="API keys are not configured")
    if not key or not any(hmac.compare_digest(key.encode(), v.encode()) for v in valid):
        raise HTTPException(
            status_code=401, detail="Invalid or missing API key", headers={"WWW-Authenticate": "ApiKey"}
        )

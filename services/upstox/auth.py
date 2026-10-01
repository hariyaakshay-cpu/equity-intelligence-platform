"""Upstox OAuth2 login flow and local token storage.

Upstox issues no refresh tokens: the access token expires around 03:30 IST the
next day, so a person must log in once per day. This module builds the login
URL, exchanges the returned code for a token, and caches the token in a
0600-permission file that the daily job reads.
"""

import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

import requests

from .client import UpstoxError

IST = ZoneInfo("Asia/Kolkata")
EXPIRY_TIME = time(3, 30)
TOKEN_FILE = Path(".upstox_token.json")


def build_login_url(client_id: str, redirect_uri: str, base_url: str = "https://api.upstox.com", state: str = "") -> str:
    """Return the URL the user opens in a browser to authorise the app."""
    params = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code"}
    if state:
        params["state"] = state
    return f"{base_url}/v2/login/authorization/dialog?{urlencode(params)}"


def extract_code(value: str) -> str:
    """Accept either the full redirect URL or the bare code and return the code."""
    value = value.strip()
    if "code=" in value:
        codes = parse_qs(urlparse(value).query).get("code")
        if not codes:
            raise UpstoxError("No 'code' parameter found in the redirect URL")
        return codes[0]
    if not value:
        raise UpstoxError("Empty authorisation code")
    return value


def exchange_code(
    code: str, client_id: str, client_secret: str, redirect_uri: str,
    base_url: str = "https://api.upstox.com", timeout: float = 30.0,
) -> str:
    """Exchange an authorisation code for an access token."""
    resp = requests.post(
        f"{base_url}/v2/login/authorization/token",
        headers={"Accept": "application/json"},
        data={
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise UpstoxError(f"Token exchange failed ({resp.status_code}): {resp.text[:200]}")
    token = resp.json().get("access_token")
    if not token:
        raise UpstoxError("Token exchange response had no access_token")
    return token


def next_expiry(now: Optional[datetime] = None) -> datetime:
    """Return the next 03:30 IST after `now`, when Upstox invalidates tokens."""
    now = now or datetime.now(IST)
    expiry = datetime.combine(now.date(), EXPIRY_TIME, tzinfo=IST)
    return expiry if expiry > now else expiry + timedelta(days=1)


def save_token(token: str, path: Path = TOKEN_FILE, now: Optional[datetime] = None) -> datetime:
    """Persist the token with its expiry; file is readable only by the owner."""
    expires = next_expiry(now)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"access_token": token, "expires_at": expires.isoformat()}, f)
    return expires


def load_token(path: Path = TOKEN_FILE, now: Optional[datetime] = None) -> Optional[str]:
    """Return the cached token, or None if missing, unreadable or expired."""
    try:
        data = json.loads(Path(path).read_text())
        expires = datetime.fromisoformat(data["expires_at"])
        token = data["access_token"]
    except (OSError, ValueError, KeyError):
        return None
    return token if expires > (now or datetime.now(IST)) else None

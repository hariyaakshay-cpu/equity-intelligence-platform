"""Tests for the Upstox OAuth helpers."""

import os
import stat
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from services.upstox import UpstoxError, auth

IST = auth.IST


def test_extract_code_from_url_and_bare():
    assert auth.extract_code("http://127.0.0.1:5000/callback?code=abc123&state=x") == "abc123"
    assert auth.extract_code(" abc123 ") == "abc123"
    with pytest.raises(UpstoxError):
        auth.extract_code("http://x/cb?code=")


def test_login_url():
    url = auth.build_login_url("cid", "http://localhost/cb", state="s")
    assert "client_id=cid" in url and "response_type=code" in url and "state=s" in url


def test_next_expiry_rolls_over():
    assert auth.next_expiry(datetime(2026, 1, 1, 1, 0, tzinfo=IST)) == datetime(2026, 1, 1, 3, 30, tzinfo=IST)
    assert auth.next_expiry(datetime(2026, 1, 1, 9, 0, tzinfo=IST)) == datetime(2026, 1, 2, 3, 30, tzinfo=IST)


def test_token_roundtrip_and_expiry(tmp_path):
    path = tmp_path / "t.json"
    now = datetime(2026, 1, 1, 9, 0, tzinfo=IST)
    auth.save_token("tok", path, now)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert auth.load_token(path, now + timedelta(hours=1)) == "tok"
    assert auth.load_token(path, now + timedelta(days=1)) is None
    assert auth.load_token(tmp_path / "missing.json") is None


def test_exchange_code():
    ok = MagicMock(status_code=200, json=lambda: {"access_token": "T"})
    with patch("services.upstox.auth.requests.post", return_value=ok) as post:
        assert auth.exchange_code("c", "id", "sec", "http://cb") == "T"
        assert post.call_args.kwargs["data"]["grant_type"] == "authorization_code"
    bad = MagicMock(status_code=401, text="nope")
    with patch("services.upstox.auth.requests.post", return_value=bad):
        with pytest.raises(UpstoxError):
            auth.exchange_code("c", "id", "sec", "http://cb")

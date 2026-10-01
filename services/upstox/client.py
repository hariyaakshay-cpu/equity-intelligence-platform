"""Thin client for the Upstox REST API (instruments and historical candles)."""

import gzip
import json
import logging
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz"


class UpstoxError(Exception):
    """Raised when the Upstox API returns an error or an unexpected payload."""


class UpstoxClient:
    """
    Client for the subset of the Upstox API needed for ingestion.

    Args:
        access_token: Upstox OAuth access token (expires daily).
        base_url: Base URL of the Upstox REST API.
        session: Optional requests session, useful for testing.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.upstox.com",
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
    ) -> None:
        if not access_token:
            raise UpstoxError("UPSTOX_ACCESS_TOKEN is not set")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        )

    def get_instruments(self, exchange: str = "NSE") -> list[dict[str, Any]]:
        """
        Download the instrument master for an exchange (public file, no auth).

        Args:
            exchange: Exchange file to fetch, e.g. 'NSE' or 'BSE'.

        Returns:
            List of instrument dicts as published by Upstox.
        """
        resp = requests.get(INSTRUMENTS_URL.format(exchange=exchange), timeout=self.timeout)
        resp.raise_for_status()
        return json.loads(gzip.decompress(resp.content))

    def get_daily_candles(
        self, instrument_key: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """
        Fetch daily OHLCV candles for an instrument.

        Args:
            instrument_key: Upstox key such as 'NSE_EQ|INE002A01018'.
            from_date: First day (inclusive).
            to_date: Last day (inclusive).

        Returns:
            List of dicts with trade_date, open, high, low, close, volume,
            sorted oldest first.
        """
        url = (
            f"{self.base_url}/v2/historical-candle/{quote(instrument_key, safe='')}"
            f"/day/{to_date.isoformat()}/{from_date.isoformat()}"
        )
        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code != 200:
            raise UpstoxError(f"Upstox {resp.status_code} for {instrument_key}: {resp.text[:200]}")
        try:
            candles = resp.json()["data"]["candles"]
        except (KeyError, TypeError, ValueError) as e:
            raise UpstoxError(f"Unexpected Upstox payload for {instrument_key}") from e

        rows = [
            {
                "trade_date": datetime.fromisoformat(c[0]).date(),
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": int(c[5]) if c[5] is not None else None,
            }
            for c in candles
        ]
        return sorted(rows, key=lambda r: r["trade_date"])

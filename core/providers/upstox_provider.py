"""
Upstox market data provider implementation for the Equity Intelligence Platform.

This provider implements the BaseDataProvider interface to fetch market data
from the Upstox API, including instruments, historical data, real-time quotes,
and option chains. It includes retry logic, proper exception handling, structured
logging, and uses credentials from the application settings.
"""

import logging
import re
from datetime import datetime, UTC
from typing import List, Dict, Optional, Any
from urllib.parse import quote
import time
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from config import Settings
from .base_provider import (
    BaseDataProvider,
    Instrument,
    HistoricalCandle,
    Quote,
    OptionChain,
    OptionContract,
)

logger = logging.getLogger(__name__)

# Custom provider-specific exceptions
class ProviderError(Exception):
    """Base exception class for all provider-related errors."""
    pass

class ProviderConnectionError(ProviderError):
    """Raised when unable to connect to the provider's API due to network issues."""
    pass

class ProviderAPIError(ProviderError):
    """Raised when the provider's API returns an error response."""
    pass

class AuthenticationError(ProviderError):
    """Raised when API authentication fails due to invalid credentials."""
    pass

class InvalidSymbolError(ProviderError):
    """Raised when an invalid or unknown instrument symbol is requested."""
    pass

class InvalidIntervalError(ProviderError):
    """Raised when an unsupported candle interval is requested."""
    pass

class InvalidExpiryError(ProviderError):
    """Raised when an invalid options expiry date is requested."""
    pass


class UpstoxProvider(BaseDataProvider):
    """
    Upstox API data provider implementation.

    This class implements the BaseDataProvider interface to interact with the
    Upstox REST API, handling authentication, retries, data normalization,
    and error handling.

    Attributes:
        settings: Application settings object containing the Upstox access token.
        base_url: Base URL for the Upstox API (v3).
        session: Authenticated requests session for API communication.
    """

    # Supported candle intervals, mapped to the V3 API's (unit, interval)
    # path-segment pair (https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/):
    # unit in {minutes, hours, days, weeks, months}; interval is numeric per unit.
    SUPPORTED_INTERVALS = {
        "1minute": ("minutes", "1"),
        "5minute": ("minutes", "5"),
        "15minute": ("minutes", "15"),
        "30minute": ("minutes", "30"),
        "1hour": ("hours", "1"),
        "1day": ("days", "1"),
    }

    # Upstox instrument_key format: "<SEGMENT>|<id>", e.g. "NSE_EQ|INE745G01043"
    # or "NSE_INDEX|Nifty 500". SEGMENT is uppercase letters/underscore; the id
    # (ISIN or index display name) may contain spaces but never a colon.
    _INSTRUMENT_KEY_SEGMENT_PATTERN = re.compile(r"^[A-Z_]+\|.+$")

    def __init__(self, settings: Settings):
        """
        Initialize the Upstox provider with application settings.

        Args:
            settings: Pydantic Settings object containing UPSTOX_ACCESS_TOKEN.

        Raises:
            ValueError: If the Upstox access token is missing from settings.
        """
        self.settings = settings
        self.base_url = "https://api.upstox.com/v3"
        self.session = self._initialize_session()
        logger.info("UpstoxProvider initialized successfully")

    def _initialize_session(self) -> requests.Session:
        """
        Create and configure an authenticated requests session.

        Returns:
            Configured requests.Session with authentication headers.

        Raises:
            ValueError: If the Upstox access token is missing from settings.
        """
        if not hasattr(self.settings, "UPSTOX_ACCESS_TOKEN") or not self.settings.UPSTOX_ACCESS_TOKEN:
            raise ValueError("UPSTOX_ACCESS_TOKEN is required in settings to use UpstoxProvider")

        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {self.settings.UPSTOX_ACCESS_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        return session

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ProviderConnectionError, ProviderAPIError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make an API request to Upstox with automatic retry logic for transient failures.

        Args:
            method: HTTP method ('GET', 'POST', etc.).
            endpoint: API endpoint path to call.
            **kwargs: Additional keyword arguments passed to requests.request().

        Returns:
            Parsed JSON response from the API.

        Raises:
            ProviderConnectionError: For network connectivity issues.
            AuthenticationError: For 401 Unauthorized responses.
            ProviderAPIError: For other API errors or non-success status codes.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"Making Upstox API request: {method} {url}")

        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Network connection error while accessing Upstox API: {e}")
            raise ProviderConnectionError(f"Failed to connect to Upstox API: {e}") from e
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout while accessing Upstox API: {e}")
            raise ProviderConnectionError(f"Upstox API request timed out: {e}") from e
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.error("Upstox API authentication failed (401 Unauthorized)")
                raise AuthenticationError("Invalid Upstox API credentials") from e
            elif response.status_code == 404:
                logger.error(f"Upstox API resource not found: {url}")
                raise ProviderAPIError(f"Requested resource not found: {url}") from e
            else:
                logger.error(f"Upstox API returned error status {response.status_code}: {response.text}")
                raise ProviderAPIError(f"Upstox API error: {response.status_code} - {response.text}") from e
        except Exception as e:
            logger.error(f"Unexpected error during Upstox API request: {e}", exc_info=True)
            raise ProviderError(f"Unexpected error: {e}") from e

    def get_instruments(self, exchange: Optional[str] = None) -> List[Instrument]:
        """
        Fetch list of all tradeable instruments from Upstox.

        Args:
            exchange: Optional exchange filter (e.g., 'NSE', 'BSE', 'NFO').

        Returns:
            List of normalized Instrument objects.

        Raises:
            ProviderConnectionError: If unable to connect to Upstox API.
            ProviderAPIError: If the API returns an error response.
            AuthenticationError: If API credentials are invalid.
        """
        logger.info(f"Fetching instruments from Upstox, exchange filter: {exchange or 'all'}")
        
        response = self._make_api_request("GET", "market/instruments")
        instruments = []

        for item in response.get("data", []):
            # Apply exchange filter if specified
            if exchange and item.get("exchange") != exchange:
                continue

            try:
                instrument = Instrument(
                    symbol=f"{item['exchange']}:{item['tradingsymbol']}",
                    name=item.get("name", ""),
                    exchange=item.get("exchange", ""),
                    instrument_type=item.get("instrument_type", ""),
                    lot_size=item.get("lot_size", 0),
                    tick_size=item.get("tick_size", 0.0),
                    instrument_token=str(item.get("instrument_token", "") or item.get("instrument_key", "")),
                    isin=item.get("isin"),
                )
                instruments.append(instrument)
            except KeyError as e:
                logger.warning(f"Skipping malformed instrument data: missing key {e}")
                continue

        logger.info(f"Successfully loaded {len(instruments)} instruments from Upstox")
        return instruments

    def get_historical_data(
        self,
        symbol: str,
        interval: str,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> List[HistoricalCandle]:
        """
        Fetch historical OHLCV candle data from Upstox's V3 historical-candle endpoint.

        Args:
            symbol: Upstox instrument_key in '<SEGMENT>|<id>' form, e.g.
                'NSE_EQ|INE745G01043' or 'NSE_INDEX|Nifty 500'.
            interval: Candle interval (must be in SUPPORTED_INTERVALS).
            start_date: Start datetime for historical data.
            end_date: End datetime, defaults to current UTC time.

        Returns:
            List of normalized HistoricalCandle objects, sorted oldest to
            newest by timestamp (the V3 API's own response ordering is not
            documented, so this method does not rely on it).

        Raises:
            InvalidIntervalError: If the requested interval is not supported.
            InvalidSymbolError: If the symbol format is invalid.
            ProviderConnectionError: If unable to connect to Upstox API.
            ProviderAPIError: If the API returns an error response.
            AuthenticationError: If API credentials are invalid.
        """
        # Validate inputs
        if interval not in self.SUPPORTED_INTERVALS:
            valid_intervals = ", ".join(self.SUPPORTED_INTERVALS.keys())
            raise InvalidIntervalError(f"Unsupported interval '{interval}'. Valid intervals: {valid_intervals}")

        if ":" in symbol or not self._INSTRUMENT_KEY_SEGMENT_PATTERN.match(symbol):
            raise InvalidSymbolError(
                "Symbol must be an Upstox instrument_key in '<SEGMENT>|<id>' form "
                "(e.g., 'NSE_EQ|INE745G01043' or 'NSE_INDEX|Nifty 500'), not ':'-delimited"
            )

        end_date = end_date or datetime.now(UTC)
        logger.info(f"Fetching historical data for {symbol} ({interval}) from {start_date.date()} to {end_date.date()}")

        # Upstox requires the instrument_key's "|" (and any spaces, e.g. in
        # index display names like "Nifty 500") percent-encoded in the URL path.
        encoded_key = quote(symbol, safe="")
        unit, v3_interval = self.SUPPORTED_INTERVALS[interval]

        # Format dates for Upstox API
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # V3 path order is to_date before from_date. Daily ("days") data is
        # documented as available from January 2000, with a maximum
        # retrieval window of 1 decade ending at to_date; this method does
        # not chunk or validate against that limit.
        endpoint = f"historical-candle/{encoded_key}/{unit}/{v3_interval}/{end_str}/{start_str}"
        response = self._make_api_request("GET", endpoint)

        candles = []
        for candle_data in response.get("data", {}).get("candles", []):
            try:
                # Upstox candle format: [timestamp, open, high, low, close, volume, open_interest]
                timestamp = datetime.fromisoformat(candle_data[0].replace("Z", "+00:00"))
                open_interest = (
                    int(candle_data[6])
                    if len(candle_data) > 6 and candle_data[6] is not None
                    else None
                )
                candle = HistoricalCandle(
                    timestamp=timestamp,
                    open=float(candle_data[1]),
                    high=float(candle_data[2]),
                    low=float(candle_data[3]),
                    close=float(candle_data[4]),
                    volume=int(candle_data[5]),
                    open_interest=open_interest,
                )
                candles.append(candle)
            except (IndexError, ValueError) as e:
                logger.warning(f"Skipping malformed candle data: {e}")
                continue

        candles.sort(key=lambda c: c.timestamp)

        logger.info(f"Successfully fetched {len(candles)} historical candles for {symbol}")
        return candles

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        Fetch real-time market quotes from Upstox for a list of symbols.

        Args:
            symbols: List of instrument symbols (must include exchange prefixes).

        Returns:
            Dictionary mapping symbols to normalized Quote objects.

        Raises:
            ProviderConnectionError: If unable to connect to Upstox API.
            ProviderAPIError: If the API returns an error response.
            AuthenticationError: If API credentials are invalid.
        """
        logger.info(f"Fetching market quotes for {len(symbols)} symbols")

        # Upstox accepts comma-separated instrument keys
        instrument_keys = ",".join(symbols)
        response = self._make_api_request("GET", f"market/quotes/{instrument_keys}")

        quotes = {}
        quote_data = response.get("data", {})

        for symbol, data in quote_data.items():
            try:
                timestamp = datetime.now(UTC)
                if "timestamp" in data:
                    timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

                quote = Quote(
                    symbol=symbol,
                    last_price=float(data.get("ltp", 0.0)),
                    high=float(data.get("high", 0.0)),
                    low=float(data.get("low", 0.0)),
                    open=float(data.get("open", 0.0)),
                    close=float(data.get("close", 0.0)),
                    volume=int(data.get("volume", 0)),
                    bid_price=float(data.get("bid_price", 0.0)),
                    ask_price=float(data.get("ask_price", 0.0)),
                    bid_quantity=int(data.get("bid_quantity", 0)),
                    ask_quantity=int(data.get("ask_quantity", 0)),
                    timestamp=timestamp,
                )
                quotes[symbol] = quote
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping malformed quote data for {symbol}: {e}")
                continue

        logger.info(f"Successfully fetched {len(quotes)} market quotes")
        return quotes

    def get_option_chain(self, symbol: str, expiry_date: Optional[datetime] = None) -> OptionChain:
        """
        Fetch the complete option chain for an underlying from Upstox.

        Args:
            symbol: Underlying symbol with exchange prefix (e.g., 'NSE:NIFTY').
            expiry_date: Optional specific expiry date to fetch.

        Returns:
            Normalized OptionChain object with all options contracts.

        Raises:
            InvalidSymbolError: If the underlying symbol is invalid.
            ProviderConnectionError: If unable to connect to Upstox API.
            ProviderAPIError: If the API returns an error response.
            AuthenticationError: If API credentials are invalid.
        """
        logger.info(f"Fetching option chain for {symbol}, expiry: {expiry_date}")

        # First get the underlying quote
        underlying_quotes = self.get_quotes([symbol])
        underlying_quote = underlying_quotes.get(symbol)

        if not underlying_quote:
            raise InvalidSymbolError(f"Could not fetch underlying data for {symbol}")

        # Fetch option chain from Upstox
        endpoint = f"market/option-chain/{symbol}"
        if expiry_date:
            expiry_str = expiry_date.strftime("%Y-%m-%d")
            endpoint += f"?expiry={expiry_str}"

        response = self._make_api_request("GET", endpoint)
        chain_data = response.get("data", {})

        # Process options contracts
        contracts = []
        strikes = chain_data.get("strikes", {})

        for strike_price, strike_data in strikes.items():
            try:
                ce_token = None
                pe_token = None
                ce_quote = None
                pe_quote = None

                # Process CE (Call) option
                ce_data = strike_data.get("CE", {})
                if ce_data:
                    ce_token = ce_data.get("instrument_key")
                    # Could fetch detailed quotes here if needed

                # Process PE (Put) option
                pe_data = strike_data.get("PE", {})
                if pe_data:
                    pe_token = pe_data.get("instrument_key")
                    # Could fetch detailed quotes here if needed

                expiry_str = chain_data.get("expiry", "")
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d") if expiry_str else datetime.now(UTC)

                contract = OptionContract(
                    strike_price=float(strike_price),
                    expiry_date=expiry,
                    ce_token=ce_token,
                    pe_token=pe_token,
                    ce_quote=ce_quote,
                    pe_quote=pe_quote,
                )
                contracts.append(contract)
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping malformed option strike {strike_price}: {e}")
                continue

        option_chain = OptionChain(
            underlying_symbol=symbol,
            underlying_quote=underlying_quote,
            contracts=contracts,
            timestamp=datetime.now(UTC),
        )

        logger.info(f"Successfully fetched option chain with {len(contracts)} strikes for {symbol}")
        return option_chain

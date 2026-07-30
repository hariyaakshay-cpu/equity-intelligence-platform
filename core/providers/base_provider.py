"""
Abstract base class defining the interface for all market data providers.

This base class establishes a common interface that all data providers must implement,
enabling seamless swapping of providers while maintaining consistent functionality
across the Equity Intelligence Platform.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any


class Instrument:
    """Normalized data transfer object representing a tradeable instrument."""
    symbol: str
    name: str
    exchange: str
    instrument_type: str
    lot_size: int
    tick_size: float
    isin: Optional[str]
    instrument_token: str

    def __init__(
        self,
        symbol: str,
        name: str,
        exchange: str,
        instrument_type: str,
        lot_size: int,
        tick_size: float,
        instrument_token: str,
        isin: Optional[str] = None,
    ):
        self.symbol = symbol
        self.name = name
        self.exchange = exchange
        self.instrument_type = instrument_type
        self.lot_size = lot_size
        self.tick_size = tick_size
        self.instrument_token = instrument_token
        self.isin = isin


class HistoricalCandle:
    """Normalized data transfer object representing OHLCV historical candle data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: Optional[int]

    def __init__(
        self,
        timestamp: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        open_interest: Optional[int] = None,
    ):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.open_interest = open_interest


class Quote:
    """Normalized data transfer object representing real-time market quote."""
    symbol: str
    last_price: float
    high: float
    low: float
    open: float
    close: float
    volume: int
    bid_price: float
    ask_price: float
    bid_quantity: int
    ask_quantity: int
    timestamp: datetime

    def __init__(
        self,
        symbol: str,
        last_price: float,
        high: float,
        low: float,
        open: float,
        close: float,
        volume: int,
        bid_price: float,
        ask_price: float,
        bid_quantity: int,
        ask_quantity: int,
        timestamp: datetime,
    ):
        self.symbol = symbol
        self.last_price = last_price
        self.high = high
        self.low = low
        self.open = open
        self.close = close
        self.volume = volume
        self.bid_price = bid_price
        self.ask_price = ask_price
        self.bid_quantity = bid_quantity
        self.ask_quantity = ask_quantity
        self.timestamp = timestamp


class OptionContract:
    """Normalized data transfer object representing a single options contract."""
    strike_price: float
    expiry_date: datetime
    ce_token: Optional[str]
    pe_token: Optional[str]
    ce_quote: Optional[Quote]
    pe_quote: Optional[Quote]

    def __init__(
        self,
        strike_price: float,
        expiry_date: datetime,
        ce_token: Optional[str] = None,
        pe_token: Optional[str] = None,
        ce_quote: Optional[Quote] = None,
        pe_quote: Optional[Quote] = None,
    ):
        self.strike_price = strike_price
        self.expiry_date = expiry_date
        self.ce_token = ce_token
        self.pe_token = pe_token
        self.ce_quote = ce_quote
        self.pe_quote = pe_quote


class OptionChain:
    """Normalized data transfer object representing a complete option chain for an underlying."""
    underlying_symbol: str
    underlying_quote: Quote
    contracts: List[OptionContract]
    timestamp: datetime

    def __init__(
        self,
        underlying_symbol: str,
        underlying_quote: Quote,
        contracts: List[OptionContract],
        timestamp: datetime,
    ):
        self.underlying_symbol = underlying_symbol
        self.underlying_quote = underlying_quote
        self.contracts = contracts
        self.timestamp = timestamp


class BaseDataProvider(ABC):
    """
    Abstract base class defining the interface for all market data providers.

    All concrete data provider implementations must inherit from this class and
    implement all abstract methods to ensure consistent behavior across providers.
    """

    @abstractmethod
    def get_instruments(self, exchange: Optional[str] = None) -> List[Instrument]:
        """
        Fetch list of all tradeable instruments from the provider.

        Args:
            exchange: Optional exchange filter to retrieve instruments only from
                     a specific exchange (e.g., 'NSE', 'BSE', 'NFO').

        Returns:
            List of normalized Instrument objects containing all instrument details.

        Raises:
            ProviderConnectionError: If unable to connect to the provider's API.
            ProviderAPIError: If the API returns an error response.
            AuthenticationError: If API credentials are invalid.
        """
        pass

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        interval: str,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> List[HistoricalCandle]:
        """
        Fetch historical OHLCV candle data for a specific instrument.

        Args:
            symbol: The instrument symbol to fetch data for.
            interval: The candle time interval (e.g., '1minute', '5minute', '1day').
            start_date: Start datetime for the historical data range.
            end_date: Optional end datetime, defaults to current UTC time if not provided.

        Returns:
            List of normalized HistoricalCandle objects containing OHLCV data.

        Raises:
            ProviderConnectionError: If unable to connect to the provider's API.
            ProviderAPIError: If the API returns an error response.
            InvalidSymbolError: If the provided symbol is not found.
            InvalidIntervalError: If the provided interval is not supported.
            AuthenticationError: If API credentials are invalid.
        """
        pass

    @abstractmethod
    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        Fetch real-time market quotes for a list of symbols.

        Args:
            symbols: List of instrument symbols to fetch quotes for.

        Returns:
            Dictionary mapping symbols to their normalized Quote objects.

        Raises:
            ProviderConnectionError: If unable to connect to the provider's API.
            ProviderAPIError: If the API returns an error response.
            InvalidSymbolError: If any of the provided symbols are not found.
            AuthenticationError: If API credentials are invalid.
        """
        pass

    @abstractmethod
    def get_option_chain(self, symbol: str, expiry_date: Optional[datetime] = None) -> OptionChain:
        """
        Fetch the complete option chain for an underlying instrument.

        Args:
            symbol: The underlying symbol (e.g., 'NSE:RELIANCE') to fetch options for.
            expiry_date: Optional specific expiry date to fetch, defaults to the nearest
                        expiry if not provided.

        Returns:
            Normalized OptionChain object containing all options contracts.

        Raises:
            ProviderConnectionError: If unable to connect to the provider's API.
            ProviderAPIError: If the API returns an error response.
            InvalidSymbolError: If the underlying symbol is not found.
            InvalidExpiryError: If the provided expiry date is invalid.
            AuthenticationError: If API credentials are invalid.
        """
        pass
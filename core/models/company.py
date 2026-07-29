"""
SQLAlchemy ORM model representing a publicly traded company.

This model stores core company information including stock symbol, exchange details,
sector classification, and timestamps for record tracking.
"""

from datetime import datetime, UTC
from typing import Optional
from sqlalchemy import Boolean, Integer, String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class Company(Base):
    """
    SQLAlchemy ORM model representing a publicly traded company.

    Attributes:
        id: Unique primary key identifier for the company
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT'), unique and indexed
        company_name: Full legal name of the company
        exchange: Stock exchange where the company is listed (e.g., 'NYSE', 'NASDAQ')
        sector: GICS sector classification
        industry: GICS industry classification
        market_cap: Current market capitalization in USD cents
        isin: International Securities Identification Number, unique
        is_active: Flag indicating if the company is still actively traded
        created_at: UTC timestamp when the record was created
        updated_at: UTC timestamp when the record was last updated
    """

    __tablename__ = "companies"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Core identifiers
    symbol: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(255))
    market_cap: Mapped[Optional[int]] = mapped_column(BigInteger)
    isin: Mapped[Optional[str]] = mapped_column(String(12), unique=True)

    # Status flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        """
        Return a string representation of the Company instance.

        Returns:
            String with company ID, symbol, and name for easy debugging
        """
        return f"<Company(id={self.id}, symbol='{self.symbol}', name='{self.company_name}')>"
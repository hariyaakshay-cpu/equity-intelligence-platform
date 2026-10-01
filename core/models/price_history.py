"""
SQLAlchemy ORM model representing daily OHLCV price data for a company.
"""

from datetime import date, datetime, UTC
from typing import Optional
from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class PriceHistory(Base):
    """
    Daily price bar for a company.

    Attributes:
        id: Unique primary key identifier
        company_id: Foreign key to the owning company
        trade_date: Trading day this bar covers
        open, high, low, close: Prices for the day
        adjusted_close: Close adjusted for splits and dividends
        volume: Number of shares traded
        source: Data provider the row came from
        created_at: UTC timestamp when the record was created
    """

    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint("company_id", "trade_date", name="uq_price_company_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    open: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))
    high: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))
    low: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))
    close: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    adjusted_close: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)

    source: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """Return a string representation of the PriceHistory instance."""
        return (
            f"<PriceHistory(company_id={self.company_id}, "
            f"date={self.trade_date}, close={self.close})>"
        )

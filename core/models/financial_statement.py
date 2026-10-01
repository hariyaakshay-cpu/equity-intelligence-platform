"""
SQLAlchemy ORM model representing a periodic financial statement for a company.
"""

from datetime import date, datetime, UTC
from typing import Optional
from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class FinancialStatement(Base):
    """
    Key income statement, balance sheet and cash flow figures for one period.

    Monetary values are stored in whole currency units (e.g. USD).

    Attributes:
        id: Unique primary key identifier
        company_id: Foreign key to the owning company
        period_end: Last day of the reporting period
        period_type: 'annual' or 'quarterly'
        fiscal_year: Fiscal year the period belongs to
        fiscal_quarter: Fiscal quarter (1-4), None for annual statements
        revenue, gross_profit, operating_income, net_income: Income statement
        eps_diluted: Diluted earnings per share
        total_assets, total_liabilities, total_equity, total_debt, cash_and_equivalents: Balance sheet
        operating_cash_flow, capital_expenditure, free_cash_flow: Cash flow
        shares_outstanding: Shares outstanding at period end
        source: Data provider the row came from
        created_at: UTC timestamp when the record was created
    """

    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_end", "period_type", name="uq_fin_company_period"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[Optional[int]] = mapped_column(Integer)

    # Income statement
    revenue: Mapped[Optional[int]] = mapped_column(BigInteger)
    gross_profit: Mapped[Optional[int]] = mapped_column(BigInteger)
    operating_income: Mapped[Optional[int]] = mapped_column(BigInteger)
    net_income: Mapped[Optional[int]] = mapped_column(BigInteger)
    eps_diluted: Mapped[Optional[float]] = mapped_column(Numeric(18, 4))

    # Balance sheet
    total_assets: Mapped[Optional[int]] = mapped_column(BigInteger)
    total_liabilities: Mapped[Optional[int]] = mapped_column(BigInteger)
    total_equity: Mapped[Optional[int]] = mapped_column(BigInteger)
    total_debt: Mapped[Optional[int]] = mapped_column(BigInteger)
    cash_and_equivalents: Mapped[Optional[int]] = mapped_column(BigInteger)

    # Cash flow
    operating_cash_flow: Mapped[Optional[int]] = mapped_column(BigInteger)
    capital_expenditure: Mapped[Optional[int]] = mapped_column(BigInteger)
    free_cash_flow: Mapped[Optional[int]] = mapped_column(BigInteger)

    shares_outstanding: Mapped[Optional[int]] = mapped_column(BigInteger)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """Return a string representation of the FinancialStatement instance."""
        return (
            f"<FinancialStatement(company_id={self.company_id}, "
            f"period_end={self.period_end}, type='{self.period_type}')>"
        )

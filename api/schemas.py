"""Pydantic response schemas for the API."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    company_name: str
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[int] = None
    isin: Optional[str] = None
    is_active: bool


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    adjusted_close: Optional[float] = None
    volume: Optional[int] = None


class FinancialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_end: date
    period_type: str
    fiscal_year: int
    fiscal_quarter: Optional[int] = None
    revenue: Optional[int] = None
    gross_profit: Optional[int] = None
    operating_income: Optional[int] = None
    net_income: Optional[int] = None
    eps_diluted: Optional[float] = None
    total_assets: Optional[int] = None
    total_liabilities: Optional[int] = None
    total_equity: Optional[int] = None
    total_debt: Optional[int] = None
    cash_and_equivalents: Optional[int] = None
    operating_cash_flow: Optional[int] = None
    capital_expenditure: Optional[int] = None
    free_cash_flow: Optional[int] = None
    shares_outstanding: Optional[int] = None

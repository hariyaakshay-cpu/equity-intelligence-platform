"""Company, price and financial statement endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.deps import get_company, get_session
from api.schemas import CompanyOut, FinancialOut, PriceOut
from core.models import Company, FinancialStatement, PriceHistory

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyOut])
def list_companies(
    q: Optional[str] = Query(None, description="Match symbol or name"),
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = select(Company).where(Company.is_active)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Company.symbol.ilike(like), Company.company_name.ilike(like)))
    if exchange:
        stmt = stmt.where(Company.exchange == exchange.upper())
    if sector:
        stmt = stmt.where(Company.sector == sector)
    return session.scalars(stmt.order_by(Company.symbol).limit(limit).offset(offset)).all()


@router.get("/{symbol}", response_model=CompanyOut)
def get_company_detail(company: Company = Depends(get_company)):
    return company


@router.get("/{symbol}/prices", response_model=list[PriceOut])
def get_prices(
    start: Optional[date] = None,
    end: Optional[date] = None,
    limit: int = Query(365, ge=1, le=5000),
    company: Company = Depends(get_company),
    session: Session = Depends(get_session),
):
    """Daily prices, newest first."""
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    stmt = select(PriceHistory).where(PriceHistory.company_id == company.id)
    if start:
        stmt = stmt.where(PriceHistory.trade_date >= start)
    if end:
        stmt = stmt.where(PriceHistory.trade_date <= end)
    return session.scalars(stmt.order_by(PriceHistory.trade_date.desc()).limit(limit)).all()


@router.get("/{symbol}/prices/latest", response_model=PriceOut)
def get_latest_price(company: Company = Depends(get_company), session: Session = Depends(get_session)):
    price = session.scalar(
        select(PriceHistory)
        .where(PriceHistory.company_id == company.id)
        .order_by(PriceHistory.trade_date.desc())
        .limit(1)
    )
    if price is None:
        raise HTTPException(status_code=404, detail=f"No prices for '{company.symbol}'")
    return price


@router.get("/{symbol}/financials", response_model=list[FinancialOut])
def get_financials(
    period_type: Optional[str] = Query(None, pattern="^(annual|quarterly)$"),
    company: Company = Depends(get_company),
    session: Session = Depends(get_session),
):
    """Financial statements, newest first."""
    stmt = select(FinancialStatement).where(FinancialStatement.company_id == company.id)
    if period_type:
        stmt = stmt.where(FinancialStatement.period_type == period_type)
    return session.scalars(stmt.order_by(FinancialStatement.period_end.desc())).all()

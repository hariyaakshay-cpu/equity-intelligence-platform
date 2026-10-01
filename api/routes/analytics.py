"""Analytics endpoints."""

import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_company, get_session
from core.models import Company, PriceHistory
from services.analytics import compute_indicators

router = APIRouter(prefix="/companies", tags=["analytics"])


@router.get("/{symbol}/indicators")
def get_indicators(company: Company = Depends(get_company), session: Session = Depends(get_session)):
    """Latest technical indicators computed from stored daily closes."""
    rows = session.execute(
        select(PriceHistory.trade_date, PriceHistory.close)
        .where(PriceHistory.company_id == company.id)
        .order_by(PriceHistory.trade_date.desc())
        .limit(400)
    ).all()
    closes = pd.Series({d: float(c) for d, c in rows}).sort_index()
    return {"symbol": company.symbol, **compute_indicators(closes)}

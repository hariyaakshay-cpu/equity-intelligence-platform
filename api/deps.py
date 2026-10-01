"""FastAPI dependencies."""

from typing import Generator

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.models import Company


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for the duration of a request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_company(symbol: str, session: Session = Depends(get_session)) -> Company:
    """Resolve a path symbol to a Company or raise 404."""
    company = session.scalar(select(Company).where(Company.symbol == symbol.upper()))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{symbol.upper()}' not found")
    return company

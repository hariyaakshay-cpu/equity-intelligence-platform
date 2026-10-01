"""Loads Upstox instruments and daily prices into the database."""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Company, PriceHistory
from services.upstox import UpstoxClient, UpstoxError

logger = logging.getLogger(__name__)

SOURCE = "upstox"


def instrument_key(company: Company, segment: str = "NSE_EQ") -> str:
    """Build the Upstox instrument key for a company from its ISIN."""
    return f"{segment}|{company.isin}"


def sync_companies(
    session: Session, client: UpstoxClient, exchange: str = "NSE", symbols: list[str] | None = None
) -> int:
    """
    Insert or update equity companies from the Upstox instrument master.

    Args:
        session: Active database session (caller commits).
        client: Upstox client.
        exchange: Exchange file to load.
        symbols: Optional allow-list of trading symbols; None loads all equities.

    Returns:
        Number of companies inserted or updated.
    """
    wanted = {s.upper() for s in symbols} if symbols else None
    existing = {c.symbol: c for c in session.scalars(select(Company))}
    count = 0
    for inst in client.get_instruments(exchange):
        if inst.get("segment") != f"{exchange}_EQ" or inst.get("instrument_type") != "EQ":
            continue
        symbol = (inst.get("trading_symbol") or "").upper()
        if not symbol or (wanted and symbol not in wanted):
            continue
        company = existing.get(symbol)
        if company is None:
            company = Company(symbol=symbol, company_name=inst.get("name") or symbol)
            session.add(company)
            existing[symbol] = company
        company.company_name = inst.get("name") or company.company_name
        company.exchange = exchange
        company.isin = inst.get("isin") or company.isin
        count += 1
    session.flush()
    logger.info("Synced %d companies from %s", count, exchange)
    return count


def sync_prices(
    session: Session, client: UpstoxClient, company: Company, from_date: date, to_date: date
) -> int:
    """
    Upsert daily candles for one company.

    Returns:
        Number of price rows inserted or updated.
    """
    if not company.isin:
        raise UpstoxError(f"{company.symbol} has no ISIN; cannot build instrument key")
    rows = client.get_daily_candles(instrument_key(company), from_date, to_date)
    existing = {
        p.trade_date: p
        for p in session.scalars(
            select(PriceHistory).where(
                PriceHistory.company_id == company.id,
                PriceHistory.trade_date.between(from_date, to_date),
            )
        )
    }
    for r in rows:
        price = existing.get(r["trade_date"])
        if price is None:
            price = PriceHistory(company_id=company.id, trade_date=r["trade_date"], close=r["close"])
            session.add(price)
        price.open, price.high, price.low = r["open"], r["high"], r["low"]
        price.close, price.volume, price.source = r["close"], r["volume"], SOURCE
    session.flush()
    return len(rows)

"""Tests for Upstox ingestion using a fake client and in-memory SQLite."""

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.database import Base
import core.models  # noqa: F401
from core.models import Company, PriceHistory
from services.ingestion import sync_companies, sync_prices


class FakeClient:
    def get_instruments(self, exchange="NSE"):
        return [
            {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "RELIANCE",
             "name": "RELIANCE INDUSTRIES LTD", "isin": "INE002A01018"},
            {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "TCS",
             "name": "TATA CONSULTANCY SERV LT", "isin": "INE467B01029"},
            {"segment": "NSE_FO", "instrument_type": "FUT", "trading_symbol": "RELIANCE24"},
        ]

    def get_daily_candles(self, key, from_date, to_date):
        assert key == "NSE_EQ|INE002A01018"
        return [
            {"trade_date": date(2026, 1, 1), "open": 1, "high": 3, "low": 1, "close": 2, "volume": 10},
            {"trade_date": date(2026, 1, 2), "open": 2, "high": 4, "low": 2, "close": 3, "volume": 20},
        ]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_sync_companies_filters_and_is_idempotent(session):
    assert sync_companies(session, FakeClient()) == 2
    assert sync_companies(session, FakeClient(), symbols=["tcs"]) == 1
    assert session.scalars(select(Company)).all().__len__() == 2


def test_sync_prices_upserts(session):
    sync_companies(session, FakeClient(), symbols=["RELIANCE"])
    company = session.scalar(select(Company))
    assert sync_prices(session, FakeClient(), company, date(2026, 1, 1), date(2026, 1, 2)) == 2
    assert sync_prices(session, FakeClient(), company, date(2026, 1, 1), date(2026, 1, 2)) == 2
    prices = session.scalars(select(PriceHistory)).all()
    assert len(prices) == 2 and prices[0].source == "upstox"


def test_daily_sync_is_incremental_and_isolates_failures(session):
    from jobs.daily_sync import run_sync

    calls = []

    class Client(FakeClient):
        def get_daily_candles(self, key, from_date, to_date):
            calls.append((key, from_date))
            if "INE467B01029" in key:
                raise RuntimeError("boom")
            return [{"trade_date": date(2026, 1, 5), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    today = date(2026, 1, 6)
    s = run_sync(session, Client(), days=10, today=today)
    assert s.companies == 2 and s.price_rows == 1 and list(s.failed) == ["TCS"]
    assert calls[0] == ("NSE_EQ|INE002A01018", date(2025, 12, 27))

    calls.clear()
    run_sync(session, Client(), skip_companies=True, today=today, symbols=["RELIANCE"])
    assert calls == [("NSE_EQ|INE002A01018", date(2026, 1, 6))]

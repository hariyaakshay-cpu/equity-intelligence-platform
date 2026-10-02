"""API tests against an in-memory SQLite database."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import core.models  # noqa: F401
from api.app import create_app
from api.auth import get_settings
from api.deps import get_session
from config import Settings
from core.database import Base
from core.models import Company, FinancialStatement, PriceHistory


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        rel = Company(symbol="RELIANCE", company_name="Reliance Industries", exchange="NSE")
        tcs = Company(symbol="TCS", company_name="Tata Consultancy", exchange="NSE")
        s.add_all([rel, tcs])
        s.flush()
        for d in (1, 2, 3):
            s.add(PriceHistory(company_id=rel.id, trade_date=date(2026, 1, d), close=100 + d))
        s.add(FinancialStatement(company_id=rel.id, period_end=date(2025, 3, 31),
                                 period_type="annual", fiscal_year=2025, revenue=10))
        s.commit()

    app = create_app()

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_settings] = lambda: Settings(API_KEYS="good-key, other-key")
    return TestClient(app, headers={"X-API-Key": "good-key"})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_and_search(client):
    assert [c["symbol"] for c in client.get("/companies").json()] == ["RELIANCE", "TCS"]
    assert [c["symbol"] for c in client.get("/companies", params={"q": "tata"}).json()] == ["TCS"]
    assert client.get("/companies", params={"limit": 0}).status_code == 422


def test_company_detail_case_insensitive_and_404(client):
    assert client.get("/companies/reliance").json()["company_name"] == "Reliance Industries"
    assert client.get("/companies/NOPE").status_code == 404


def test_prices(client):
    rows = client.get("/companies/RELIANCE/prices").json()
    assert [r["trade_date"] for r in rows] == ["2026-01-03", "2026-01-02", "2026-01-01"]
    rows = client.get("/companies/RELIANCE/prices", params={"start": "2026-01-02", "end": "2026-01-02"}).json()
    assert len(rows) == 1
    assert client.get("/companies/RELIANCE/prices", params={"start": "2026-02-01", "end": "2026-01-01"}).status_code == 422
    assert client.get("/companies/RELIANCE/prices/latest").json()["close"] == 103.0
    assert client.get("/companies/TCS/prices/latest").status_code == 404


def test_financials(client):
    rows = client.get("/companies/RELIANCE/financials", params={"period_type": "annual"}).json()
    assert rows[0]["revenue"] == 10
    assert client.get("/companies/RELIANCE/financials", params={"period_type": "x"}).status_code == 422


def test_indicators_endpoint(client):
    r = client.get("/companies/RELIANCE/indicators").json()
    assert r["symbol"] == "RELIANCE" and r["observations"] == 3 and r["close"] == 103.0
    assert r["sma_20"] is None
    assert client.get("/companies/TCS/indicators").json()["observations"] == 0
    assert client.get("/companies/NOPE/indicators").status_code == 404


def test_auth_required_and_health_open(client):
    assert client.get("/health", headers={"X-API-Key": ""}).status_code == 200
    for path in ("/companies", "/companies/RELIANCE/indicators"):
        assert client.get(path, headers={"X-API-Key": ""}).status_code == 401
        assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/companies", headers={"X-API-Key": "other-key"}).status_code == 200


def test_fails_closed_without_configured_keys(client):
    client.app.dependency_overrides[get_settings] = lambda: Settings(API_KEYS="")
    assert client.get("/companies").status_code == 503

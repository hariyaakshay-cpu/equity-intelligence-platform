"""FastAPI application factory.

Run with: uvicorn api.app:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import analytics, companies
from config import Settings
from config.logging_config import setup_logging
from core.database import initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    setup_logging(settings)
    initialize_database(settings)
    yield


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    app.include_router(companies.router)
    app.include_router(analytics.router)
    return app


app = create_app()

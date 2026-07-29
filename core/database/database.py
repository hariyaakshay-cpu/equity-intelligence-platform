"""
Initializes the SQLAlchemy engine and provides a database initialization function.
"""

import logging
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from config import Settings
from .session import SessionLocal

logger = logging.getLogger(__name__)

engine: Optional[Engine] = None


def initialize_database(settings: Settings) -> None:
    """
    Initializes the database engine and binds it to the session factory.

    This function creates a synchronous SQLAlchemy engine, handles potential
    connection errors, and binds the engine to the sessionmaker to enable
    proper session creation.

    Args:
        settings: The application settings object containing the DATABASE_URL.

    Raises:
        SQLAlchemyError: If the database connection fails.
    """
    global engine
    if engine is not None:
        logger.warning("Database engine is already initialized.")
        return

    try:
        engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_pre_ping=True,
        )
        # Bind the engine to the sessionmaker only after engine is initialized
        SessionLocal.configure(bind=engine)
        logger.info("Database engine initialized successfully and bound to session factory.")
    except SQLAlchemyError as e:
        logger.error(f"Failed to initialize database engine: {e}")
        raise


def get_engine() -> Engine:
    """
    Returns the initialized SQLAlchemy engine.

    Returns:
        The SQLAlchemy engine instance.

    Raises:
        RuntimeError: If the engine is not initialized.
    """
    if engine is None:
        raise RuntimeError("Database engine has not been initialized.")
    return engine
"""
Manages SQLAlchemy sessions for database interactions.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Initialize sessionmaker without binding an engine at import time
# Engine will be bound after database initialization
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Provides a transactional scope around a series of database operations.

    This context manager handles the session lifecycle, including creation,
    commit, and rollback. It verifies the engine is properly bound before
    attempting to create a session.

    Yields:
        The SQLAlchemy Session object.

    Raises:
        RuntimeError: If the database engine has not been initialized and bound.
        SQLAlchemyError: If an error occurs during the transaction.
    """

    # Verify engine is bound before creating a session
    if SessionLocal.kw.get("bind") is None:
        raise RuntimeError(
            "Database engine has not been initialized. Call initialize_database() first."
        )

    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database transaction failed: {e}")
        raise
    finally:
        session.close()
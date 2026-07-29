"""
Defines the declarative base for SQLAlchemy models.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.

    This class provides a common foundation for all database models,
    allowing them to be automatically discovered and managed by SQLAlchemy.
    """

    pass
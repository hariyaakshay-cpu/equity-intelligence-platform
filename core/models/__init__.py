"""Initializes the models package so all models register with Base.metadata."""

from .company import Company
from .price_history import PriceHistory

__all__ = ["Company", "PriceHistory"]

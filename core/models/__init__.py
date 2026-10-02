"""
Package containing all SQLAlchemy ORM models for the Equity Intelligence Platform.

All models must be imported here to ensure they are registered with the SQLAlchemy
Base metadata, which is required for Alembic autogenerate to detect model changes.
"""

# Import all models to register them with Base.metadata
from .company import Company

# Add new models here as they are created:
# from .price_history import PriceHistory
# from .corporate_action import CorporateAction
# from .fundamental import Fundamental
# from .technical_indicator import TechnicalIndicator
# from .scanner_result import ScannerResult

__all__ = [
    "Company",
    # Add new models to __all__ as they are created
    # "PriceHistory",
    # "CorporateAction",
    # "Fundamental",
    # "TechnicalIndicator",
    # "ScannerResult",
]
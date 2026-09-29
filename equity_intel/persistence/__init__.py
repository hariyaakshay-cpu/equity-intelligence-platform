"""Equity Intelligence persistence.

The E1-E3 research acquisition database is opened only by the guarded
``persistence.connection`` module at the canonical ``data/equity_intel.db``
path. It is independent of the application's ORM and all trading stores.
"""

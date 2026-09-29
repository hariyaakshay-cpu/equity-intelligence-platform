"""Persistence layer for data/equity_intel.db.

equity_intel/persistence/connection.py is the one module in this package
(and in equity_intel/ as a whole) authorized to import sqlite3 -- see
equity_intel/tests/test_db_connection_boundary.py. Every connection it opens
is validated against db_path_guard.py's canonical path first. No module
here contains a hardcoded path to any existing OMS/trading database, and
none of schema.py's DDL references a broker/OMS table or a B2 threshold.
"""

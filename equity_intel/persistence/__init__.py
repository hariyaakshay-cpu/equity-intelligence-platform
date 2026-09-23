"""Persistence layer -- schema definitions and abstract repositories only.

This subpackage does NOT create data/equity_intel.db. No module here opens
a database connection, writes a file, or contains a hardcoded path to any
existing OMS/trading database. The schema below is DDL text only, provided
so its shape can be reviewed and parsed (e.g. in an in-memory SQLite
connection, which persists nothing to disk) before a real database is ever
created by a separately authorized task.
"""

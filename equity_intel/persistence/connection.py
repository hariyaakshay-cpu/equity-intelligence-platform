"""The only on-disk SQLite connection for Equity Intelligence."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from equity_intel.persistence.db_path_guard import CANONICAL_DB_PATH, assert_allowed_db_path

ACQUISITION_SCHEMA = """
CREATE TABLE IF NOT EXISTS acquisition_runs (
 run_id TEXT PRIMARY KEY, run_started_at TEXT NOT NULL, run_completed_at TEXT,
 status TEXT NOT NULL, report_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS instrument_mappings (
 run_id TEXT NOT NULL, symbol TEXT NOT NULL, exchange TEXT NOT NULL,
 instrument_key TEXT, instrument_type TEXT, mapping_status TEXT NOT NULL,
 mapping_source TEXT NOT NULL, mapping_error TEXT, company_name TEXT, industry TEXT,
 series TEXT, isin TEXT, PRIMARY KEY (run_id, symbol)
);
CREATE TABLE IF NOT EXISTS acquired_observations (
 run_id TEXT NOT NULL, symbol TEXT NOT NULL, trading_date TEXT NOT NULL,
 open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL,
 source_vendor TEXT NOT NULL, source_endpoint TEXT NOT NULL, retrieval_timestamp TEXT NOT NULL,
 instrument_key TEXT NOT NULL, exchange TEXT NOT NULL, calendar_status TEXT NOT NULL,
 adjustment_status TEXT NOT NULL, data_version TEXT NOT NULL,
 PRIMARY KEY (run_id, symbol, trading_date, source_vendor)
);
CREATE TABLE IF NOT EXISTS symbol_acquisition_results (
 run_id TEXT NOT NULL, symbol TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
 instrument_key TEXT, observation_count INTEGER NOT NULL, first_date TEXT, last_date TEXT,
 requested_start TEXT, requested_end TEXT, validation_status TEXT,
 PRIMARY KEY (run_id, symbol)
);
"""


def connect(path: str | Path = CANONICAL_DB_PATH) -> sqlite3.Connection:
    """Open the guarded canonical database and ensure E1-E3 tables exist."""
    allowed = assert_allowed_db_path(path)
    allowed.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(allowed), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(ACQUISITION_SCHEMA)
        connection.commit()
    except Exception:
        connection.close()
        raise
    return connection

"""equity_intel's single sqlite3 connection module.

Hosts both the E1-E4 acquisition/feature tables (connect(), created with
CREATE TABLE IF NOT EXISTS) and the scanner V1 tables (get_connection(),
get_read_only_connection(), initialize_schema() -- versioned via schema.py).

This is the one module inside equity_intel/ authorized to import sqlite3 --
equity_intel/tests/test_db_connection_boundary.py enforces this via static
analysis. Every connection function here validates its target path through
equity_intel.persistence.db_path_guard.assert_allowed_db_path before opening
anything, per docs/architecture/equity_intel_boundary_decision.md, Section 5.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

from equity_intel.persistence.db_path_guard import CANONICAL_DB_PATH, assert_allowed_db_path
from equity_intel.persistence.schema import SCHEMA_STATEMENTS, SCHEMA_VERSION

PathLike = Union[str, Path]


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
CREATE TABLE IF NOT EXISTS e4_scan_runs (
 scan_id TEXT PRIMARY KEY, acquisition_run_id TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
 status TEXT NOT NULL, asof_date TEXT, calendar_status TEXT, constituents_sha256 TEXT, instrument_master_sha256 TEXT,
 indicator_config_json TEXT NOT NULL, failure_reason TEXT
);
CREATE TABLE IF NOT EXISTS e4_data_quality_results (
 scan_id TEXT NOT NULL, symbol TEXT NOT NULL, status TEXT NOT NULL, reason TEXT, n_bars INTEGER,
 w52_complete INTEGER, break_date TEXT, break_ratio REAL, volume_usable INTEGER,
 PRIMARY KEY (scan_id, symbol)
);
CREATE TABLE IF NOT EXISTS e4_feature_sets (
 scan_id TEXT NOT NULL, symbol TEXT NOT NULL, last_date TEXT,
 ema_short REAL, ema_medium REAL, ema_long REAL, rsi REAL, roc REAL, relative_volume REAL,
 distance_from_high REAL, prior_high_long REAL, atr_percent REAL,
 PRIMARY KEY (scan_id, symbol)
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


def get_connection(path: PathLike = CANONICAL_DB_PATH) -> sqlite3.Connection:
    """Open a writable connection to the one canonical equity_intel database.

    Used by the scanner (the writer side). Does not initialize the schema;
    call initialize_schema() on the returned connection if needed. Foreign
    keys are off by default per sqlite3 connection, so this turns them on
    explicitly -- without it, schema.py's REFERENCES clauses (e.g.
    price_fetch_snapshots.scan_run_id -> scan_runs.run_id) would be silently
    unenforced.
    """
    resolved = assert_allowed_db_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_read_only_connection(path: PathLike = CANONICAL_DB_PATH) -> sqlite3.Connection:
    """Open a read-only connection to the one canonical equity_intel database.

    Used by the read-only dashboard, which must never write. The path is
    validated as a real file path first via assert_allowed_db_path;
    the sqlite3 URI ("file:...?mode=ro") is constructed only afterward, for
    the connect() call itself -- assert_allowed_db_path never receives the
    URI form (it explicitly refuses "file:"-prefixed strings as not being a
    real file path -- see db_path_guard.py). Foreign keys are turned on for
    consistency with get_connection(), even though a read-only connection
    can never trigger an FK-enforced write in the first place.
    """
    resolved = assert_allowed_db_path(path)
    uri = f"file:{resolved.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class SchemaVersionMismatch(RuntimeError):
    """Raised when data/equity_intel.db's schema_version does not match the
    SCHEMA_VERSION this code expects. Never silently ignored: a mismatch
    means either the code or the database is stale relative to the other,
    and proceeding could silently write into (or read from) the wrong
    column shapes.
    """


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create every table in SCHEMA_STATEMENTS if the database is not yet
    initialized (its schema_version table is absent). Idempotent: a no-op
    on an already-initialized database whose recorded version matches
    SCHEMA_VERSION exactly; raises SchemaVersionMismatch otherwise -- never
    a silent no-op on a version mismatch.

    All table/trigger creation happens inside one explicit transaction
    (BEGIN/COMMIT, with an explicit ROLLBACK on failure): sqlite3's default
    commit()/rollback() do NOT undo DDL statements (CREATE TABLE is
    auto-committed as it runs), so an explicit transaction is required for
    a failure partway through to leave no partial schema behind.
    """
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if existing is not None:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise SchemaVersionMismatch(
                f"data/equity_intel.db has schema_version {version}, "
                f"but this code expects SCHEMA_VERSION {SCHEMA_VERSION}"
            )
        return

    conn.execute("BEGIN")
    try:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, datetime('now'))",
            (SCHEMA_VERSION,),
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")

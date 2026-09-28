"""equity_intel's single sqlite3 connection module.

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

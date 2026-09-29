"""Tests for equity_intel.persistence.connection.

None of these tests point at the real data/equity_intel.db:
db_path_guard.CANONICAL_DB_PATH is monkeypatched to a tmp_path location for
every test, following the same pattern as test_db_path_guard.py's
test_accepts_a_monkeypatched_tmp_path_canonical. This file imports sqlite3
only to reference exception types (sqlite3.OperationalError,
sqlite3.IntegrityError) raised by the connection module -- it never calls
sqlite3.connect() itself; every real connection goes through
equity_intel.persistence.connection.
"""
import sqlite3

import pytest

from equity_intel.persistence import connection, db_path_guard
from equity_intel.persistence.schema import SCHEMA_VERSION


@pytest.fixture
def temp_db_path(monkeypatch, tmp_path):
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    return path


def test_get_connection_refuses_a_non_canonical_path(tmp_path):
    with pytest.raises(ValueError):
        connection.get_connection(tmp_path / "not_canonical.db")


def test_get_connection_opens_the_monkeypatched_canonical_path(temp_db_path):
    conn = connection.get_connection(temp_db_path)
    try:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    finally:
        conn.close()
    assert temp_db_path.exists()


def test_get_connection_enables_foreign_keys(temp_db_path):
    conn = connection.get_connection(temp_db_path)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_get_read_only_connection_enables_foreign_keys(temp_db_path):
    writer = connection.get_connection(temp_db_path)
    try:
        connection.initialize_schema(writer)
    finally:
        writer.close()

    reader = connection.get_read_only_connection(temp_db_path)
    try:
        assert reader.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        reader.close()


def test_initialize_schema_creates_every_table(temp_db_path):
    conn = connection.get_connection(temp_db_path)
    try:
        connection.initialize_schema(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for expected in ("schema_version", "scan_runs", "price_fetch_snapshots", "symbol_scan_results"):
            assert expected in tables
    finally:
        conn.close()


def test_initialize_schema_is_idempotent(temp_db_path):
    conn = connection.get_connection(temp_db_path)
    try:
        connection.initialize_schema(conn)
        connection.initialize_schema(conn)  # must not raise "table already exists"
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_initialize_schema_raises_on_version_mismatch_not_silently(temp_db_path):
    conn = connection.get_connection(temp_db_path)
    try:
        connection.initialize_schema(conn)
        conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))
        conn.commit()
        with pytest.raises(connection.SchemaVersionMismatch):
            connection.initialize_schema(conn)
    finally:
        conn.close()


def test_initialize_schema_leaves_no_partial_schema_on_failure(temp_db_path, monkeypatch):
    broken_statements = ("CREATE TABLE ok_table (x INTEGER)", "THIS IS NOT VALID SQL")
    monkeypatch.setattr(connection, "SCHEMA_STATEMENTS", broken_statements)

    conn = connection.get_connection(temp_db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.initialize_schema(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "ok_table" not in tables
        assert "schema_version" not in tables
    finally:
        conn.close()


def test_price_fetch_snapshot_insert_fails_for_a_nonexistent_scan_run(temp_db_path):
    conn = connection.get_connection(temp_db_path)
    try:
        connection.initialize_schema(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO price_fetch_snapshots
                    (scan_run_id, symbol, trading_date, source, fetched_at_ist, content_hash, candle_validation_status)
                VALUES ('does-not-exist', 'TCS', '2026-09-25', 'upstox', 't', 'hash', 'VALID')
                """
            )
    finally:
        conn.close()


def test_symbol_scan_result_insert_fails_for_a_nonexistent_scan_run(temp_db_path):
    conn = connection.get_connection(temp_db_path)
    try:
        connection.initialize_schema(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO symbol_scan_results (scan_run_id, symbol, symbol_data_status) "
                "VALUES ('does-not-exist', 'TCS', 'VALID')"
            )
    finally:
        conn.close()


def test_get_read_only_connection_refuses_a_non_canonical_path(tmp_path):
    with pytest.raises(ValueError):
        connection.get_read_only_connection(tmp_path / "not_canonical.db")


def test_get_read_only_connection_can_read_but_not_write(temp_db_path):
    writer = connection.get_connection(temp_db_path)
    try:
        connection.initialize_schema(writer)
    finally:
        writer.close()

    reader = connection.get_read_only_connection(temp_db_path)
    try:
        row = reader.execute("SELECT version FROM schema_version").fetchone()
        assert row[0] == SCHEMA_VERSION
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("INSERT INTO schema_version (version, applied_at) VALUES (99, 'x')")
    finally:
        reader.close()


def test_get_read_only_connection_works_when_the_path_contains_a_space(monkeypatch, tmp_path):
    path_with_space = tmp_path / "Equity - intraday" / "equity_intel.db"
    path_with_space.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path_with_space)

    writer = connection.get_connection(path_with_space)
    try:
        connection.initialize_schema(writer)
    finally:
        writer.close()

    reader = connection.get_read_only_connection(path_with_space)
    try:
        row = reader.execute("SELECT version FROM schema_version").fetchone()
        assert row[0] == SCHEMA_VERSION
    finally:
        reader.close()

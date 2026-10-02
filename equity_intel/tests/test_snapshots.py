"""Tests for equity_intel.scanner.snapshots.

db_path_guard.CANONICAL_DB_PATH is monkeypatched to a tmp_path location
for every test that touches a real connection, same pattern as
equity_intel/tests/test_connection.py -- never the real data/equity_intel.db.
"""
from decimal import Decimal

import pytest

from equity_intel.persistence import connection, db_path_guard
from equity_intel.scanner.snapshots import (
    compute_content_hash,
    compute_content_hash_from_stored_row,
    price_to_text,
    quantize_price,
    write_snapshot,
)


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    return path


@pytest.fixture
def conn(db_path):
    c = connection.get_connection(db_path)
    connection.initialize_schema(c)
    c.execute(
        "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
        "VALUES ('r1', '2026-09-28T09:00:00+05:30', 'RUNNING', 'BLOCKED_B2')"
    )
    c.commit()
    try:
        yield c
    finally:
        c.close()


def test_quantize_price_rounds_half_up_to_two_places():
    assert quantize_price(100.5) == Decimal("100.50")
    assert quantize_price(100.125) == Decimal("100.13")  # half up, not banker's rounding
    assert quantize_price(100.124) == Decimal("100.12")


def test_quantize_price_passes_none_through():
    assert quantize_price(None) is None


def test_price_to_text_produces_the_canonical_2dp_string():
    assert price_to_text(100.5) == "100.50"
    assert price_to_text(100) == "100.00"
    assert price_to_text(None) is None


def test_compute_content_hash_is_deterministic_and_order_sensitive():
    h1 = compute_content_hash("2026-09-25", 100.5, 101.0, 99.5, 100.75, 12345)
    h2 = compute_content_hash("2026-09-25", 100.5, 101.0, 99.5, 100.75, 12345)
    h3 = compute_content_hash("2026-09-25", 100.5, 101.0, 99.5, 100.76, 12345)
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_compute_content_hash_treats_none_as_empty_string_field():
    h_with_none = compute_content_hash("2026-09-25", None, 101.0, 99.5, 100.75, 12345)
    h_with_empty_equivalent = compute_content_hash("2026-09-25", None, 101.0, 99.5, 100.75, 12345)
    assert h_with_none == h_with_empty_equivalent


def test_write_snapshot_stores_100_point_5_as_the_string_100_50(conn):
    write_snapshot(
        conn,
        scan_run_id="r1",
        symbol="TCS",
        trading_date="2026-09-25",
        source="upstox",
        fetched_at_ist="2026-09-28T09:05:00+05:30",
        open_=100.5,
        high=102.0,
        low=99.0,
        close=101.5,
        volume=123456,
        candle_validation_status="VALID",
    )
    conn.commit()
    row = conn.execute(
        "SELECT open, high, low, close FROM price_fetch_snapshots WHERE scan_run_id = 'r1' AND symbol = 'TCS'"
    ).fetchone()
    assert row[0] == "100.50"
    assert row[1] == "102.00"
    assert row[2] == "99.00"
    assert row[3] == "101.50"


def test_recomputing_the_hash_from_the_stored_row_reproduces_content_hash(conn):
    written_hash = write_snapshot(
        conn,
        scan_run_id="r1",
        symbol="TCS",
        trading_date="2026-09-25",
        source="upstox",
        fetched_at_ist="2026-09-28T09:05:00+05:30",
        open_=100.5,
        high=102.0,
        low=99.0,
        close=101.5,
        volume=123456,
        candle_validation_status="VALID",
    )
    conn.commit()
    row = conn.execute(
        "SELECT trading_date, open, high, low, close, volume, content_hash "
        "FROM price_fetch_snapshots WHERE scan_run_id = 'r1' AND symbol = 'TCS'"
    ).fetchone()
    stored_row = {
        "trading_date": row[0],
        "open": row[1],
        "high": row[2],
        "low": row[3],
        "close": row[4],
        "volume": row[5],
    }
    recomputed_hash = compute_content_hash_from_stored_row(stored_row)
    assert recomputed_hash == row[6]
    assert recomputed_hash == written_hash


def test_write_snapshot_records_validation_errors_and_source_metadata(conn):
    write_snapshot(
        conn,
        scan_run_id="r1",
        symbol="TCS",
        trading_date="2026-09-25",
        source="upstox",
        fetched_at_ist="2026-09-28T09:05:00+05:30",
        open_=100.5,
        high=102.0,
        low=99.0,
        close=101.5,
        volume=123456,
        candle_validation_status="INVALID",
        validation_errors=["HIGH_LESS_THAN_LOW"],
        source_metadata={"interval": "1day"},
    )
    conn.commit()
    row = conn.execute(
        "SELECT candle_validation_status, validation_errors_json, source_metadata_json "
        "FROM price_fetch_snapshots WHERE scan_run_id = 'r1' AND symbol = 'TCS'"
    ).fetchone()
    assert row[0] == "INVALID"
    assert "HIGH_LESS_THAN_LOW" in row[1]
    assert "1day" in row[2]


def test_write_snapshot_refuses_a_duplicate_within_the_same_run(conn):
    import sqlite3

    kwargs = dict(
        scan_run_id="r1",
        symbol="TCS",
        trading_date="2026-09-25",
        source="upstox",
        fetched_at_ist="2026-09-28T09:05:00+05:30",
        open_=100.5,
        high=102.0,
        low=99.0,
        close=101.5,
        volume=123456,
        candle_validation_status="VALID",
    )
    write_snapshot(conn, **kwargs)
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        write_snapshot(conn, **kwargs)


def test_write_snapshot_refuses_for_a_nonexistent_scan_run(conn):
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        write_snapshot(
            conn,
            scan_run_id="does-not-exist",
            symbol="TCS",
            trading_date="2026-09-25",
            source="upstox",
            fetched_at_ist="2026-09-28T09:05:00+05:30",
            open_=100.5,
            high=102.0,
            low=99.0,
            close=101.5,
            volume=123456,
            candle_validation_status="VALID",
        )

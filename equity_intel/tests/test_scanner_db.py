"""Tests for equity_intel.scanner.db -- the scanner's canonical-only write path.

db_path_guard.CANONICAL_DB_PATH and DEMO_DB_PATH are monkeypatched to
tmp_path locations for every test, same pattern as
equity_intel/tests/test_connection.py -- never the real data/equity_intel.db
or a real data/equity_intel_demo.db.
"""
import pytest

from equity_intel.persistence import db_path_guard
from equity_intel.scanner.db import RefusedNonCanonicalDatabaseError, get_scan_connection


@pytest.fixture
def paths(monkeypatch, tmp_path):
    canonical = tmp_path / "equity_intel.db"
    demo = tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", canonical)
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    return canonical, demo


def test_opens_the_canonical_path_by_default(paths):
    canonical, _demo = paths
    conn = get_scan_connection()
    try:
        assert canonical.exists()
    finally:
        conn.close()


def test_opens_the_canonical_path_when_given_explicitly(paths):
    canonical, _demo = paths
    conn = get_scan_connection(canonical)
    try:
        assert canonical.exists()
    finally:
        conn.close()


def test_refuses_the_demo_database_path(paths):
    _canonical, demo = paths
    with pytest.raises(RefusedNonCanonicalDatabaseError):
        get_scan_connection(demo)
    assert not demo.exists()


def test_refuses_an_arbitrary_path(paths, tmp_path):
    _canonical, _demo = paths
    arbitrary = tmp_path / "some_other.db"
    with pytest.raises(RefusedNonCanonicalDatabaseError):
        get_scan_connection(arbitrary)
    assert not arbitrary.exists()


def test_enables_foreign_keys(paths):
    conn = get_scan_connection()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()

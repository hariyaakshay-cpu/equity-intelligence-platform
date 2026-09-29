"""Tests for the equity_intel database-path allow-list guard.

No test here ever opens a real database connection -- these tests only
call assert_allowed_db_path() to check whether a given path would be
accepted or refused, and never pass an accepted path to sqlite3.connect.
"""
import os
from pathlib import Path

import pytest

from equity_intel.persistence import db_path_guard
from equity_intel.persistence.db_path_guard import CANONICAL_DB_PATH, DEMO_DB_PATH, assert_allowed_db_path


@pytest.mark.parametrize(
    "forbidden_name", ["oms_state.db", "oms_shadow.db", "production_trading.db"]
)
def test_refuses_known_forbidden_database_names(tmp_path, forbidden_name):
    forbidden_path = tmp_path / forbidden_name
    with pytest.raises(ValueError):
        assert_allowed_db_path(forbidden_path)


def test_refuses_equity_intel_db_under_algo_trader():
    forbidden_path = Path(r"C:\Users\Akshay\algo_trader\data\equity_intel.db")
    with pytest.raises(ValueError):
        assert_allowed_db_path(forbidden_path)


def test_refuses_equity_intel_db_in_a_different_directory(tmp_path):
    forbidden_path = tmp_path / "equity_intel.db"
    with pytest.raises(ValueError):
        assert_allowed_db_path(forbidden_path)


def test_refuses_a_relative_path_when_cwd_is_not_the_repo_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        assert_allowed_db_path("./data/equity_intel.db")


def test_refuses_memory_shorthand():
    with pytest.raises(ValueError):
        assert_allowed_db_path(":memory:")


def test_refuses_sqlite_uri_shorthand():
    with pytest.raises(ValueError):
        assert_allowed_db_path("file:equity_intel.db?mode=rw")


def test_refuses_a_symlink_pointing_at_a_forbidden_file(tmp_path):
    forbidden_target = tmp_path / "oms_state.db"
    forbidden_target.write_text("")
    symlink_path = tmp_path / "equity_intel.db"
    try:
        os.symlink(forbidden_target, symlink_path)
    except OSError:
        pytest.skip("symlink creation is not permitted in this environment")
    with pytest.raises(ValueError):
        assert_allowed_db_path(symlink_path)


def test_accepts_the_canonical_path():
    result = assert_allowed_db_path(CANONICAL_DB_PATH)
    assert result == CANONICAL_DB_PATH.resolve(strict=False)


def test_accepts_a_case_variant_of_the_canonical_path():
    variant = Path(str(CANONICAL_DB_PATH).upper())
    result = assert_allowed_db_path(variant)
    assert result == CANONICAL_DB_PATH.resolve(strict=False)


def test_accepts_a_monkeypatched_tmp_path_canonical(monkeypatch, tmp_path):
    patched_canonical = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", patched_canonical)
    result = assert_allowed_db_path(patched_canonical)
    assert result == patched_canonical.resolve(strict=False)


def test_accepts_the_demo_path():
    result = assert_allowed_db_path(DEMO_DB_PATH)
    assert result == DEMO_DB_PATH.resolve(strict=False)


def test_refuses_a_sibling_of_the_demo_path_in_the_same_directory(tmp_path):
    forbidden_path = DEMO_DB_PATH.parent / "equity_intel_demo.db.bak"
    with pytest.raises(ValueError):
        assert_allowed_db_path(forbidden_path)


def test_refuses_the_demo_db_name_in_a_different_directory(tmp_path):
    forbidden_path = tmp_path / "equity_intel_demo.db"
    with pytest.raises(ValueError):
        assert_allowed_db_path(forbidden_path)

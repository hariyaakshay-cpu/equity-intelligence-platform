"""Tests for equity_intel.scanner.scan_lock. Every test uses a tmp_path
lock file path -- never the real data/equity_intel_scan.lock."""
import json
from datetime import datetime

import pytest

from equity_intel.config import IST
from equity_intel.scanner.scan_lock import ScannerAlreadyRunningError, acquire_scan_lock, release_scan_lock

_NOW = datetime(2026, 9, 29, 9, 0, 0, tzinfo=IST)


def test_acquire_scan_lock_creates_a_file_with_pid_and_started_at(tmp_path):
    path = tmp_path / "scan.lock"
    acquire_scan_lock(path, now=_NOW)
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "pid" in payload
    assert payload["started_at"] == _NOW.isoformat()


def test_acquire_scan_lock_raises_if_the_file_already_exists(tmp_path):
    path = tmp_path / "scan.lock"
    acquire_scan_lock(path, now=_NOW)
    with pytest.raises(ScannerAlreadyRunningError) as excinfo:
        acquire_scan_lock(path, now=_NOW)
    message = str(excinfo.value)
    # The refusal shows the existing lock's contents and how to clear it.
    assert str(path) in message
    assert "pid" in message
    assert "delete this file" in message.lower()


def test_acquire_scan_lock_never_overwrites_an_existing_file(tmp_path):
    path = tmp_path / "scan.lock"
    path.write_text('{"pid": 12345, "started_at": "2020-01-01T00:00:00+05:30"}', encoding="utf-8")
    with pytest.raises(ScannerAlreadyRunningError):
        acquire_scan_lock(path, now=_NOW)
    # Untouched -- still the original (stale) contents, not overwritten.
    assert json.loads(path.read_text(encoding="utf-8"))["pid"] == 12345


def test_release_scan_lock_removes_the_file(tmp_path):
    path = tmp_path / "scan.lock"
    acquire_scan_lock(path, now=_NOW)
    release_scan_lock(path)
    assert not path.exists()


def test_release_scan_lock_is_a_noop_if_the_file_is_already_gone(tmp_path):
    path = tmp_path / "scan.lock"
    release_scan_lock(path)  # must not raise
    assert not path.exists()

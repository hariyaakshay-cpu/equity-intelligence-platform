"""Tests for equity_intel.scanner.instrument_master.

No test touches the network. fetch_and_save_instrument_master and
fetch_instrument_master (the two functions that call requests.get) are
exercised against a local http server-free fake by monkeypatching
requests.get itself -- everything else works against a small fixture
.json.gz built in-memory (gzip.compress over a handful of rows shaped
like the real file: one NSE_EQ/EQ match, one NSE_FO row, one BSE row, one
row with a missing ISIN), written to tmp_path so load_instrument_master
exercises real file I/O without touching the repo's data/reference/.
"""
import gzip
import hashlib
import json
from datetime import datetime

import pytest
import requests

from equity_intel.scanner import instrument_master as im
from equity_intel.scanner.instrument_master import (
    InstrumentMasterUnavailableError,
    fetch_and_save_instrument_master,
    fetch_instrument_master,
    load_instrument_master,
)

_FIXTURE_ROWS = [
    {"segment": "NSE_EQ", "instrument_type": "EQ", "isin": "INE1", "instrument_key": "NSE_EQ|INE1", "name": "A"},
    {"segment": "NSE_FO", "instrument_type": "FUT", "isin": "INE2", "instrument_key": "NSE_FO|INE2", "name": "B"},
    {"segment": "BSE_EQ", "instrument_type": "EQ", "isin": "INE3", "instrument_key": "BSE_EQ|INE3", "name": "C"},
    {"segment": "NSE_EQ", "instrument_type": "EQ", "isin": None, "instrument_key": "NSE_EQ|INE4", "name": "D"},
]

_FIXED_NOW = datetime(2026, 9, 28, 9, 0, 0, tzinfo=im.IST)


def _fixture_bytes() -> bytes:
    return gzip.compress(json.dumps(_FIXTURE_ROWS).encode("utf-8"))


def _sha8(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


@pytest.fixture
def fixture_path(tmp_path):
    path = tmp_path / "fixture_NSE.json.gz"
    path.write_bytes(_fixture_bytes())
    return path


def test_load_instrument_master_reads_rows_and_computes_sha256(fixture_path):
    master = load_instrument_master(fixture_path)
    assert master.rows == _FIXTURE_ROWS
    assert master.total_rows == 4
    assert master.source == str(fixture_path)
    assert len(master.file_sha256) == 64  # hex sha256 digest length


def test_load_instrument_master_uses_explicit_source_when_given(fixture_path):
    master = load_instrument_master(fixture_path, source="https://example.test/NSE.json.gz")
    assert master.source == "https://example.test/NSE.json.gz"


def test_load_instrument_master_raises_on_missing_file(tmp_path):
    with pytest.raises(InstrumentMasterUnavailableError):
        load_instrument_master(tmp_path / "does_not_exist.json.gz")


def test_load_instrument_master_raises_on_invalid_gzip(tmp_path):
    bad_path = tmp_path / "not_gzip.json.gz"
    bad_path.write_bytes(b"this is not gzip data")
    with pytest.raises(InstrumentMasterUnavailableError):
        load_instrument_master(bad_path)


def test_load_instrument_master_raises_when_json_root_is_not_a_list(tmp_path):
    bad_path = tmp_path / "wrong_shape.json.gz"
    bad_path.write_bytes(gzip.compress(json.dumps({"not": "a list"}).encode("utf-8")))
    with pytest.raises(InstrumentMasterUnavailableError):
        load_instrument_master(bad_path)


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(f"{self.status_code} error")


def test_fetch_and_save_instrument_master_filename_includes_date_and_sha256_prefix(monkeypatch, tmp_path):
    monkeypatch.setattr(im.requests, "get", lambda url, timeout: _FakeResponse(_fixture_bytes()))
    dest_dir = tmp_path / "reference"

    path = fetch_and_save_instrument_master(dest_dir, now=_FIXED_NOW)

    expected_name = f"upstox_NSE_instruments_2026-09-28_{_sha8(_fixture_bytes())}.json.gz"
    assert path == dest_dir / expected_name
    assert path.read_bytes() == _fixture_bytes()


def test_fetch_and_save_instrument_master_second_download_same_day_does_not_collide(monkeypatch, tmp_path):
    # Two downloads on the same calendar day, with different content, must
    # land at two different filenames -- neither overwrites the other, so
    # a provenance record pointing at the first file's path still resolves
    # to the exact bytes it was computed from.
    dest_dir = tmp_path / "reference"
    content_a = _fixture_bytes()
    content_b = gzip.compress(json.dumps(_FIXTURE_ROWS[:1]).encode("utf-8"))
    assert content_a != content_b

    monkeypatch.setattr(im.requests, "get", lambda url, timeout: _FakeResponse(content_a))
    path_a = fetch_and_save_instrument_master(dest_dir, now=_FIXED_NOW)

    monkeypatch.setattr(im.requests, "get", lambda url, timeout: _FakeResponse(content_b))
    path_b = fetch_and_save_instrument_master(dest_dir, now=_FIXED_NOW)

    assert path_a != path_b
    assert path_a.read_bytes() == content_a
    assert path_b.read_bytes() == content_b


def test_fetch_and_save_instrument_master_raises_on_request_exception(monkeypatch, tmp_path):
    def _raise(url, timeout):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(im.requests, "get", _raise)
    with pytest.raises(InstrumentMasterUnavailableError):
        fetch_and_save_instrument_master(tmp_path / "reference")


def test_fetch_and_save_instrument_master_raises_on_non_200(monkeypatch, tmp_path):
    monkeypatch.setattr(im.requests, "get", lambda url, timeout: _FakeResponse(b"", status_code=404))
    with pytest.raises(InstrumentMasterUnavailableError):
        fetch_and_save_instrument_master(tmp_path / "reference")


def test_fetch_instrument_master_downloads_saves_and_loads_in_one_step(monkeypatch, tmp_path):
    monkeypatch.setattr(im.requests, "get", lambda url, timeout: _FakeResponse(_fixture_bytes()))
    dest_dir = tmp_path / "reference"

    master = fetch_instrument_master(dest_dir, url="https://example.test/NSE.json.gz", now=_FIXED_NOW)

    assert master.rows == _FIXTURE_ROWS
    assert master.source == "https://example.test/NSE.json.gz"  # the URL, not the local cache path
    expected_name = f"upstox_NSE_instruments_2026-09-28_{_sha8(_fixture_bytes())}.json.gz"
    assert (dest_dir / expected_name).exists()

"""Tests for equity_intel.scanner.instrument_mapping.

Every "raw row" here is a plain local dict shaped like the real Upstox
NSE.json.gz file (see instrument_master.py's docstring) -- no test
touches the network or downloads anything for real.
"""
import pytest

from equity_intel.persistence import connection, db_path_guard
from equity_intel.scanner.instrument_mapping import (
    INSTRUMENT_MAP_EMPTY,
    build_isin_instrument_map,
    map_universe_isins,
    record_instrument_map_provenance,
)
from equity_intel.scanner.instrument_master import InstrumentMaster


def _row(segment, instrument_type, isin, instrument_key):
    return {"segment": segment, "instrument_type": instrument_type, "isin": isin, "instrument_key": instrument_key}


def _master(rows, *, source="test-source", fetched_at="2026-09-28T09:00:00+05:30", file_sha256="deadbeef"):
    return InstrumentMaster(rows=rows, source=source, fetched_at=fetched_at, file_sha256=file_sha256, total_rows=len(rows))


def test_maps_nse_eq_instruments_by_isin():
    raw = [_row("NSE_EQ", "EQ", "INE745G01043", "NSE_EQ|INE745G01043")]
    mapping = build_isin_instrument_map(raw)
    assert mapping.isin_to_instrument_key == {"INE745G01043": "NSE_EQ|INE745G01043"}


def test_excludes_non_nse_eq_segment():
    raw = [_row("BSE_EQ", "EQ", "INE1", "BSE_EQ|INE1")]
    mapping = build_isin_instrument_map(raw)
    assert mapping.isin_to_instrument_key == {}


def test_excludes_other_instrument_types():
    raw = [_row("NSE_EQ", "SG", "INE1", "NSE_EQ|INE1")]  # e.g. a sovereign gold bond row
    mapping = build_isin_instrument_map(raw)
    assert mapping.isin_to_instrument_key == {}


def test_maps_be_instrument_type():
    # BE-series rows must resolve, not just get flagged elsewhere -- the
    # universe rule is "flag non-EQ series, never exclude" (see module
    # docstring; this mirrors HFCL's real row in the live file).
    raw = [_row("NSE_EQ", "BE", "INE548A01028", "NSE_EQ|INE548A01028")]
    mapping = build_isin_instrument_map(raw)
    assert mapping.isin_to_instrument_key == {"INE548A01028": "NSE_EQ|INE548A01028"}


def test_prefers_eq_over_be_when_one_isin_has_both():
    raw = [
        _row("NSE_EQ", "BE", "INE1", "NSE_EQ|BE_VARIANT"),
        _row("NSE_EQ", "EQ", "INE1", "NSE_EQ|EQ_VARIANT"),
    ]
    mapping = build_isin_instrument_map(raw)
    assert mapping.isin_to_instrument_key == {"INE1": "NSE_EQ|EQ_VARIANT"}

    # Order in the file must not matter -- EQ still wins when it comes first.
    raw_reversed = list(reversed(raw))
    mapping_reversed = build_isin_instrument_map(raw_reversed)
    assert mapping_reversed.isin_to_instrument_key == {"INE1": "NSE_EQ|EQ_VARIANT"}


def test_excludes_instruments_with_no_isin():
    raw = [_row("NSE_EQ", "EQ", None, "NSE_EQ|X"), _row("NSE_EQ", "EQ", "", "NSE_EQ|Y")]
    mapping = build_isin_instrument_map(raw)
    assert mapping.isin_to_instrument_key == {}


def test_maps_multiple_instruments():
    raw = [
        _row("NSE_EQ", "EQ", "INE1", "NSE_EQ|INE1"),
        _row("NSE_EQ", "EQ", "INE2", "NSE_EQ|INE2"),
        _row("BSE_EQ", "EQ", "INE3", "BSE_EQ|INE3"),
    ]
    mapping = build_isin_instrument_map(raw)
    assert mapping.isin_to_instrument_key == {
        "INE1": "NSE_EQ|INE1",
        "INE2": "NSE_EQ|INE2",
    }


def test_empty_input_yields_empty_map():
    mapping = build_isin_instrument_map([])
    assert mapping.isin_to_instrument_key == {}


def test_map_universe_isins_reports_counts_and_unmatched_isins():
    raw = [
        _row("NSE_EQ", "EQ", "INE1", "NSE_EQ|INE1"),
        _row("NSE_EQ", "BE", "INE2", "NSE_EQ|INE2"),  # BE accepted -- counted and mapped
        _row("BSE_EQ", "EQ", "INE3", "BSE_EQ|INE3"),  # not NSE_EQ -- excluded
        _row("NSE_EQ", "SG", "INE4", "NSE_EQ|INE4"),  # not EQ/BE -- excluded
    ]
    master = _master(raw, source="https://example.test/NSE.json.gz", file_sha256="abc123")
    mapping, provenance = map_universe_isins(master, ["INE1", "INE2", "INE9"])

    assert mapping.isin_to_instrument_key == {"INE1": "NSE_EQ|INE1", "INE2": "NSE_EQ|INE2"}
    assert provenance.source == "https://example.test/NSE.json.gz"
    assert provenance.fetched_at == "2026-09-28T09:00:00+05:30"
    assert provenance.file_sha256 == "abc123"
    assert provenance.total_instruments == 4
    assert provenance.nse_eq_count == 2
    assert provenance.matched_count == 2
    assert provenance.unmatched_isins == ["INE9"]
    assert provenance.is_empty is False


def test_map_universe_isins_is_empty_when_nothing_matches():
    raw = [_row("BSE_EQ", "EQ", "INE1", "BSE_EQ|INE1")]
    _mapping, provenance = map_universe_isins(_master(raw), ["INE1"])
    assert provenance.matched_count == 0
    assert provenance.is_empty is True
    assert provenance.unmatched_isins == ["INE1"]
    # The reason Phase 3's ScanRun lifecycle should use to abort the run:
    assert INSTRUMENT_MAP_EMPTY == "INSTRUMENT_MAP_EMPTY"


@pytest.fixture
def conn(monkeypatch, tmp_path):
    path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", path)
    c = connection.get_connection(path)
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


def test_record_instrument_map_provenance_persists_json_on_the_scan_run(conn):
    raw = [_row("NSE_EQ", "EQ", "INE1", "NSE_EQ|INE1")]
    _mapping, provenance = map_universe_isins(_master(raw), ["INE1", "INE2"])

    record_instrument_map_provenance(conn, run_id="r1", provenance=provenance)
    conn.commit()

    row = conn.execute(
        "SELECT instrument_map_provenance_json FROM scan_runs WHERE run_id = 'r1'"
    ).fetchone()
    assert row[0] is not None
    assert "INE2" in row[0]  # the unmatched ISIN is visible in the stored JSON
    assert '"matched_count": 1' in row[0]

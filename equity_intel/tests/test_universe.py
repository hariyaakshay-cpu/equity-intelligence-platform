"""Tests for equity_intel.scanner.universe.

Runs against the real committed data/reference/nifty500_constituents_*.csv
(no network, no fabricated fixture needed) plus a couple of small
synthetic CSVs for edge cases -- no test touches the network or any
database.
"""
from pathlib import Path

from equity_intel.scanner.universe import load_universe, sha256_file

REAL_CSV = Path(__file__).resolve().parents[2] / "data" / "reference" / "nifty500_constituents_2026-09-24.csv"


def test_loads_the_real_constituents_csv_with_known_counts():
    universe = load_universe(REAL_CSV)
    assert len(universe.members) == 500
    assert len(universe.excluded_symbols) == 1


def test_excludes_dummy_symbol_with_reason():
    universe = load_universe(REAL_CSV)
    assert universe.excluded_symbols[0].symbol == "DUMMYHEG"
    assert universe.excluded_symbols[0].reason == "DUMMY_SYMBOL"
    assert all(m.symbol != "DUMMYHEG" for m in universe.members)


def test_flags_non_eq_series_without_excluding():
    universe = load_universe(REAL_CSV)
    hfcl = next(m for m in universe.members if m.symbol == "HFCL")
    assert hfcl.series == "BE"
    assert hfcl.non_eq_series_flag is True


def test_eq_series_members_are_not_flagged():
    universe = load_universe(REAL_CSV)
    reliance = next(m for m in universe.members if m.symbol == "RELIANCE")
    assert reliance.series == "EQ"
    assert reliance.non_eq_series_flag is False


def test_universe_version_is_the_csv_sha256():
    universe = load_universe(REAL_CSV)
    assert universe.universe_version == sha256_file(REAL_CSV)
    assert len(universe.universe_version) == 64


def test_sector_comes_from_industry_column():
    universe = load_universe(REAL_CSV)
    abb = next(m for m in universe.members if m.symbol == "ABB")
    assert abb.sector == "Capital Goods"


def test_a_dummy_prefixed_symbol_with_different_casing_is_still_excluded(tmp_path):
    csv_path = tmp_path / "mini.csv"
    csv_path.write_text(
        "Company Name,Industry,Symbol,Series,ISIN Code\n"
        "Dummy Co,Sector,dummyfoo,EQ,INE000000001\n"
        "Real Co,Sector,REALCO,EQ,INE000000002\n"
    )
    universe = load_universe(csv_path)
    assert len(universe.members) == 1
    assert universe.members[0].symbol == "REALCO"
    assert universe.excluded_symbols[0].symbol == "dummyfoo"


def test_two_different_csv_contents_hash_differently(tmp_path):
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text("Company Name,Industry,Symbol,Series,ISIN Code\nX,Y,SYM,EQ,INE1\n")
    b.write_text("Company Name,Industry,Symbol,Series,ISIN Code\nX,Y,SYM,EQ,INE2\n")
    assert load_universe(a).universe_version != load_universe(b).universe_version


def test_identical_csv_contents_hash_identically(tmp_path):
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    content = "Company Name,Industry,Symbol,Series,ISIN Code\nX,Y,SYM,EQ,INE1\n"
    a.write_text(content)
    b.write_text(content)
    assert load_universe(a).universe_version == load_universe(b).universe_version

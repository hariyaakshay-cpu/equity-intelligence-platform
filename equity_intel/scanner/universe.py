"""Universe loading from the NIFTY 500 constituents CSV.

Per docs/architecture/equity_intel_scanner_v1_spec.md Section 2: exclude
any row whose Symbol matches DUMMY*; flag (never exclude) any row whose
Series is not EQ. Excluded rows and their reason are recorded on the
ScanRun (excluded_symbols), not silently dropped -- this module returns
them as data, it does not log-and-forget them.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    company_name: str
    sector: str
    series: str
    isin: str
    non_eq_series_flag: bool


@dataclass(frozen=True)
class ExcludedSymbol:
    symbol: str
    reason: str


@dataclass(frozen=True)
class Universe:
    members: List[UniverseMember]
    excluded_symbols: List[ExcludedSymbol]
    universe_version: str  # SHA-256 hex digest of the CSV file, unmodified


def sha256_file(path: Union[str, Path]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_universe(csv_path: Union[str, Path]) -> Universe:
    """Parse the constituents CSV into a Universe.

    Columns (per the committed data/reference/nifty500_constituents_*.csv
    and docs/architecture/equity_scanner_v1_design.md Section 2): "Company
    Name", "Industry" (-> sector), "Symbol", "Series", "ISIN Code".
    """
    path = Path(csv_path)
    universe_version = sha256_file(path)

    members: List[UniverseMember] = []
    excluded: List[ExcludedSymbol] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row["Symbol"].strip()
            if symbol.upper().startswith("DUMMY"):
                excluded.append(ExcludedSymbol(symbol=symbol, reason="DUMMY_SYMBOL"))
                continue
            series = row["Series"].strip()
            members.append(
                UniverseMember(
                    symbol=symbol,
                    company_name=row["Company Name"].strip(),
                    sector=row["Industry"].strip(),
                    series=series,
                    isin=row["ISIN Code"].strip(),
                    non_eq_series_flag=(series != "EQ"),
                )
            )

    return Universe(members=members, excluded_symbols=excluded, universe_version=universe_version)

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from equity_intel.acquisition.models import Constituent

SYMBOL_RE = re.compile(r"^[A-Z0-9&._-]{1,32}$")
REQUIRED_COLUMNS = {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}


class UniverseError(ValueError):
    pass


def normalize_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol or not SYMBOL_RE.fullmatch(symbol):
        raise ValueError(f"Malformed NSE symbol: {value!r}")
    return symbol


def load_universe(path: str | Path) -> tuple[list[Constituent], list[Constituent], str]:
    source = Path(path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    eligible: list[Constituent] = []
    excluded: list[Constituent] = []
    seen: set[str] = set()
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise UniverseError(f"Constituent CSV missing required columns: {sorted(REQUIRED_COLUMNS)}")
        for row_number, row in enumerate(reader, start=2):
            raw = (row.get("Symbol") or "").strip()
            try:
                symbol = normalize_symbol(raw)
                issue = None
            except ValueError as error:
                symbol, issue = raw.upper(), str(error)
            record = Constituent(symbol, row.get("Company Name", "").strip(), row.get("Industry", "").strip(),
                                 row.get("Series", "").strip().upper(), row.get("ISIN Code", "").strip().upper(), row_number, issue)
            if symbol in seen:
                raise UniverseError(f"Duplicate constituent symbol {symbol!r} at CSV row {row_number}")
            seen.add(symbol)
            (excluded if symbol.startswith("DUMMY") else eligible).append(record)
    return eligible, excluded, digest

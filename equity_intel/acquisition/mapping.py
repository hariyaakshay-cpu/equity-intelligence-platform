from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from equity_intel.acquisition.models import Constituent, MappingRecord


def load_instrument_master(path: str | Path) -> tuple[list[dict[str, Any]], str]:
    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, list):
        raise ValueError("Upstox instrument master must be a JSON array")
    return payload, digest


def map_constituents(constituents: list[Constituent], instruments: list[dict[str, Any]], source_name: str) -> list[MappingRecord]:
    by_isin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for instrument in instruments:
        if instrument.get("segment") != "NSE_EQ" or instrument.get("exchange") not in ("NSE", "NSE_EQ"):
            continue
        # Keep BE series too: they are trade-for-trade/no-intraday, but this
        # pipeline requests daily historical candles and must report the flag.
        if instrument.get("instrument_type") not in {"EQ", "BE"}:
            continue
        isin = str(instrument.get("isin") or "").strip().upper()
        symbol = str(instrument.get("trading_symbol") or "").strip().upper()
        if isin:
            by_isin[isin].append(instrument)
        if symbol:
            by_symbol[symbol].append(instrument)

    records: list[MappingRecord] = []
    for member in constituents:
        matches = by_isin.get(member.isin, []) if member.isin else []
        match_basis = "ISIN"
        if not matches and member.normalization_error is None:
            matches = by_symbol.get(member.symbol, [])
            match_basis = "symbol fallback"
        if member.normalization_error:
            records.append(MappingRecord(member.symbol, "NSE", None, None, "INVALID_INSTRUMENT", source_name,
                                         member.normalization_error, member.company_name, member.industry, member.series, member.isin))
        elif len(matches) == 1:
            instrument = matches[0]
            key = str(instrument.get("instrument_key") or "")
            valid = key.startswith("NSE_EQ|") and bool(key.split("|", 1)[1])
            records.append(MappingRecord(member.symbol, "NSE", key if valid else None,
                str(instrument.get("instrument_type") or "EQ"), "MAPPED" if valid else "INVALID_INSTRUMENT", source_name,
                None if valid else "Matched instrument has invalid/missing Upstox instrument_key", member.company_name,
                member.industry, member.series, member.isin))
        elif len(matches) > 1:
            records.append(MappingRecord(member.symbol, "NSE", None, None, "AMBIGUOUS", source_name,
                f"{len(matches)} NSE_EQ instruments matched by {match_basis}", member.company_name, member.industry, member.series, member.isin))
        else:
            records.append(MappingRecord(member.symbol, "NSE", None, None, "UNMAPPED", source_name,
                "No NSE_EQ instrument matched by ISIN or exact symbol", member.company_name, member.industry, member.series, member.isin))
    return records

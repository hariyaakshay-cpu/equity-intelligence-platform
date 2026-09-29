"""ISIN -> Upstox instrument_key mapping, from the Upstox instrument master.

Per docs/architecture/equity_intel_scanner_v1_spec.md Section 2: instrument
mapping is by ISIN, against the Upstox NSE_EQ-segment instrument master. A
symbol whose ISIN has no instrument-master match is never dropped from the
universe -- Phase 3's classification is responsible for turning that into
a FAILED symbol_data_status naming the unmatched ISIN; this module only
reports which ISINs matched and which did not.

The instrument master itself is downloaded/loaded by
equity_intel.scanner.instrument_master (see that module's docstring for
why -- Upstox's v3 REST instrument endpoint 404s live; the real master is
a public static gzip JSON file). This module only filters its rows.

Filter: raw row's "segment" == "NSE_EQ" and "instrument_type" in ("EQ",
"BE"), matched by "isin", using "instrument_key" as the resolved value.
BE is accepted, not just flagged, because the frozen spec's universe rule
is "flag non-EQ series, never exclude" (universe.py already sets
non_eq_series_flag=True for a BE-series symbol; it must still resolve to
a real instrument_key here, not silently drop out as unmapped). Confirmed
against the real file (fetched 2026-09-28): HFCL's own row has segment
NSE_EQ, instrument_type BE, isin INE548A01028 -- there is no separate EQ
row for HFCL's ISIN in the file, so this repo's 500-symbol universe now
resolves 500/500 (was 499/500 before BE was accepted). If a single ISIN
ever has both an EQ row and a BE row, EQ wins (see _TYPE_PRIORITY) -- BE
is a fallback for symbols with no EQ row, not a competing source of
truth. Every other instrument_type (SG, GS, N0, ... -- there are over a
hundred in the real file) is still ignored, as is any non-NSE_EQ segment.
Each row is a plain dict with (at least) segment, name, exchange, isin,
instrument_type, instrument_key, lot_size, freeze_quantity,
exchange_token, tick_size, trading_symbol, qty_multiplier, security_type.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List

from equity_intel.scanner.instrument_master import InstrumentMaster

NSE_EQ_SEGMENT = "NSE_EQ"
EQ_INSTRUMENT_TYPE = "EQ"
BE_INSTRUMENT_TYPE = "BE"

# Lower wins when one ISIN appears in more than one accepted-instrument_type
# row (EQ preferred over BE -- see module docstring).
_TYPE_PRIORITY = {EQ_INSTRUMENT_TYPE: 0, BE_INSTRUMENT_TYPE: 1}

# Recorded as scan_runs.abort_reason (a free-text column, not a CHECK-
# constrained enum -- see equity_intel/persistence/schema.py) when a run's
# instrument-master fetch produced zero ISIN matches against the universe.
# Wiring the actual RUNNING -> ABORTED transition is Phase 3's ScanRun
# lifecycle work; this module only computes whether that condition holds
# (InstrumentMapProvenance.is_empty) and exposes the reason string Phase 3
# should use.
INSTRUMENT_MAP_EMPTY = "INSTRUMENT_MAP_EMPTY"


@dataclass(frozen=True)
class InstrumentMapping:
    isin_to_instrument_key: Dict[str, str]


@dataclass(frozen=True)
class InstrumentMapProvenance:
    """Provenance for one run's instrument-master fetch, persisted onto
    scan_runs.instrument_map_provenance_json so a run that matched zero or
    unexpectedly few ISINs is diagnosable after the fact, not just visible
    as a pass/fail abort_reason."""

    source: str  # the instrument master's URL or local file path
    fetched_at: str  # IST, +05:30 offset
    file_sha256: str  # of the raw downloaded/given .json.gz file
    total_instruments: int  # every row the instrument master file contains, before any filter
    nse_eq_count: int  # rows matching segment == NSE_EQ and instrument_type in ("EQ", "BE")
    matched_count: int  # of the universe's ISINs, how many resolved to an instrument_key
    unmatched_isins: List[str]  # universe ISINs with no instrument-master match, sorted

    @property
    def is_empty(self) -> bool:
        return self.matched_count == 0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "fetched_at": self.fetched_at,
            "file_sha256": self.file_sha256,
            "total_instruments": self.total_instruments,
            "nse_eq_count": self.nse_eq_count,
            "matched_count": self.matched_count,
            "unmatched_isins": self.unmatched_isins,
        }


def _is_accepted(row: dict) -> bool:
    return row.get("segment") == NSE_EQ_SEGMENT and row.get("instrument_type") in _TYPE_PRIORITY


def build_isin_instrument_map(raw_rows: Iterable[dict]) -> InstrumentMapping:
    """raw_rows: the rows of an InstrumentMaster (equity_intel.scanner.
    instrument_master) -- plain dicts as parsed from the real file's JSON,
    not an object with attributes. This function does no fetching or
    parsing itself, so it is trivially testable without any network access.

    When one ISIN has both an accepted EQ row and an accepted BE row, the
    EQ row wins -- see _TYPE_PRIORITY and the module docstring.
    """
    best: Dict[str, tuple] = {}  # isin -> (priority, instrument_key)
    for row in raw_rows:
        if not _is_accepted(row):
            continue
        isin = row.get("isin")
        if not isin:
            continue
        priority = _TYPE_PRIORITY[row.get("instrument_type")]
        existing = best.get(isin)
        if existing is None or priority < existing[0]:
            best[isin] = (priority, row.get("instrument_key"))

    mapping = {isin: instrument_key for isin, (_priority, instrument_key) in best.items()}
    return InstrumentMapping(isin_to_instrument_key=mapping)


def map_universe_isins(
    master: InstrumentMaster,
    universe_isins: Iterable[str],
) -> "tuple[InstrumentMapping, InstrumentMapProvenance]":
    """Build the ISIN map and, in the same pass, the provenance record for
    it: how many raw rows the instrument master had, how many survived the
    NSE_EQ segment + (EQ or BE) filter, and -- against this run's actual
    universe -- how many of its ISINs matched versus which ones did not.
    """
    universe_isins = list(universe_isins)

    mapping = build_isin_instrument_map(master.rows)
    nse_eq_count = sum(1 for row in master.rows if _is_accepted(row))
    unmatched = sorted(
        isin for isin in set(universe_isins) if isin not in mapping.isin_to_instrument_key
    )
    matched_count = len(set(universe_isins)) - len(unmatched)

    provenance = InstrumentMapProvenance(
        source=master.source,
        fetched_at=master.fetched_at,
        file_sha256=master.file_sha256,
        total_instruments=master.total_rows,
        nse_eq_count=nse_eq_count,
        matched_count=matched_count,
        unmatched_isins=unmatched,
    )
    return mapping, provenance


def record_instrument_map_provenance(conn, *, run_id: str, provenance: InstrumentMapProvenance) -> None:
    """Persist `provenance` onto an in-progress (RUNNING) scan_run row.

    A plain UPDATE, not an insert -- the row already exists (created at
    run start, per Section 9's ScanRun lifecycle). schema.py's
    prevent_finished_scan_run_update trigger only allows this while the
    row is still RUNNING, which is always true at the point in a scan
    where the instrument map is built.
    """
    conn.execute(
        "UPDATE scan_runs SET instrument_map_provenance_json = ? WHERE run_id = ?",
        (json.dumps(provenance.to_dict()), run_id),
    )

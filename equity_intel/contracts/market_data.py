"""Market-data contracts.

These describe the SHAPE of an OHLCV observation and a universe member
record, per the field names used (without endorsement) in the prior,
non-authoritative Equity Intelligence design material and in
B2_AUTHORITATIVE_SCORING_SPECIFICATION_2026-09-22.md Section 3 ("Persisted
inputs consumed"). No vendor, exchange feed, or universe source is selected
by this module -- these are pure data shapes with no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class OHLCVObservation:
    """One daily bar for one instrument.

    `open` is intentionally omitted as a required field name collision risk
    with the Python builtin is avoided; B2 Section 3 states `open` is never
    used by any component, so it is not modeled here at all.
    """

    instrument_id: str
    observation_date: date
    high: float
    low: float
    close: float
    volume: Optional[float]


@dataclass(frozen=True)
class InstrumentMember:
    """One universe member record.

    Field names intentionally mirror the concepts named in the prior design
    material (symbol identity, human name, sector, active flag) without
    selecting a source, vendor, or taxonomy for any of them. `sector` is a
    free-form string, not a constrained enum of any specific taxonomy
    (GICS, NSE's own classification, or otherwise) -- see the Structural
    Build Boundary Audit Section 8 ("sector taxonomy" finding).
    """

    symbol: str
    exchange_symbol: Optional[str] = None
    secondary_vendor_ticker: Optional[str] = None
    instrument_key: Optional[str] = None
    isin: Optional[str] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    active: Optional[bool] = None


@dataclass(frozen=True)
class BenchmarkObservation:
    """One daily close for a benchmark series.

    Which index (NIFTY 500 or otherwise) serves as the benchmark is an
    unresolved B3/B2 decision (B2 spec D03/D04's HUMAN-DECISION row on
    benchmark choice). This contract records a close for *a* benchmark
    identified by `benchmark_id`; it does not select one.
    """

    benchmark_id: str
    observation_date: date
    close: float

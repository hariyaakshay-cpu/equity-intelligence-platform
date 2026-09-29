from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class Constituent:
    symbol: str
    company_name: str
    industry: str
    series: str
    isin: str
    source_row: int
    normalization_error: str | None = None


@dataclass(frozen=True)
class MappingRecord:
    symbol: str
    exchange: str
    instrument_key: str | None
    instrument_type: str | None
    mapping_status: str
    mapping_source: str
    mapping_error: str | None = None
    company_name: str = ""
    industry: str = ""
    series: str = ""
    isin: str = ""


@dataclass(frozen=True)
class Candle:
    trading_date: date | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


@dataclass(frozen=True)
class ValidationResult:
    status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass
class SymbolResult:
    symbol: str
    status: str
    reason: str | None = None
    instrument_key: str | None = None
    observation_count: int = 0
    first_date: str | None = None
    last_date: str | None = None
    requested_start: str | None = None
    requested_end: str | None = None
    validation_status: str | None = None
    warnings: list[str] = field(default_factory=list)
    persisted_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class AcquisitionReport:
    run_id: str
    run_started_at: str
    run_completed_at: str | None
    universe_count: int
    mapped_count: int
    unmapped_count: int
    excluded_count: int
    requested_count: int
    successful_count: int
    no_data_count: int
    request_failed_count: int
    validation_failed_count: int
    insufficient_history_count: int
    persisted_symbol_count: int
    persisted_observation_count: int
    required_sessions: int
    requested_start: str
    requested_end: str
    calendar_status: str = "PROVISIONAL"
    calendar_basis: str = "Upstox returned daily observation dates; no official NSE calendar applied"
    source_vendor: str = "Upstox"
    source_endpoint: str = "GET https://api.upstox.com/v3/historical-candle/{instrument_key}/days/1/{to_date}/{from_date}"
    adjustment_status: str = "Upstox daily series is split-adjusted; demergers are not adjusted"
    constituents_sha256: str = ""
    instrument_master_sha256: str = ""
    status: str = "RUNNING"
    symbols: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

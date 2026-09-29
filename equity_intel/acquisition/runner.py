from __future__ import annotations

import time
import uuid
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from core.providers.upstox_provider import AuthenticationError
from equity_intel.acquisition.mapping import load_instrument_master, map_constituents
from equity_intel.acquisition.models import AcquisitionReport, Candle, MappingRecord, SymbolResult
from equity_intel.acquisition.persistence import (finish_run, save_benchmark, save_mappings, save_observations,
                                                    save_run_start, save_symbol_result)
from equity_intel.acquisition.reporting import write_report
from equity_intel.acquisition.universe import load_universe
from equity_intel.acquisition.validation import validate_candles

REQUIRED_SESSIONS = 252
CALENDAR_LOOKBACK_DAYS = 500
IST = ZoneInfo("Asia/Kolkata")


def _to_candles(raw: list[object]) -> list[Candle]:
    candles: list[Candle] = []
    for item in raw:
        stamp = item.timestamp
        if isinstance(stamp, datetime):
            trading_date = stamp.date()
        elif isinstance(stamp, date):
            trading_date = stamp
        else:
            trading_date = None
        values = []
        for name in ("open", "high", "low", "close", "volume"):
            try:
                value = getattr(item, name)
                values.append(None if value is None else float(value))
            except (AttributeError, TypeError, ValueError, OverflowError):
                values.append(None)
        candles.append(Candle(trading_date, *values))
    return candles


def _failure(record: MappingRecord) -> SymbolResult:
    status = "MAPPING_FAILED" if record.mapping_status != "MAPPED" else "REQUEST_FAILED"
    return SymbolResult(record.symbol, status, record.mapping_error, record.instrument_key)


def run_equity_data_acquisition(
    provider,
    universe_path: str | Path,
    instrument_master_path: str | Path,
    *,
    end_date: date | None = None,
    start_date: date | None = None,
    run_id: str | None = None,
    required_sessions: int = REQUIRED_SESSIONS,
    pacing_seconds: float = 0.2,
    sleeper: Callable[[float], None] = time.sleep,
    db_path: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> AcquisitionReport:
    """Acquire, validate, persist, and report research OHLCV, per constituent.

    `provider` must implement the existing UpstoxProvider historical-data
    interface. No scoring or order/trading interface is used here.
    """
    if required_sessions < 1 or pacing_seconds < 0:
        raise ValueError("required_sessions must be positive and pacing_seconds non-negative")
    started_dt = datetime.now(timezone.utc)
    today_ist = datetime.now(IST).date()
    requested_end = end_date or today_ist
    requested_start = start_date or requested_end - timedelta(days=CALENDAR_LOOKBACK_DAYS)
    if requested_start > requested_end:
        raise ValueError("start_date must not be after end_date")
    resolved_run_id = run_id or f"eqdata-{started_dt.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    members, excluded, constituents_hash = load_universe(universe_path)
    master, master_hash = load_instrument_master(instrument_master_path)
    mappings = map_constituents(members, master, Path(instrument_master_path).name)
    report = AcquisitionReport(
        run_id=resolved_run_id, run_started_at=started_dt.isoformat(), run_completed_at=None,
        universe_count=len(members), mapped_count=sum(m.mapping_status == "MAPPED" for m in mappings),
        unmapped_count=sum(m.mapping_status != "MAPPED" for m in mappings), excluded_count=len(excluded),
        requested_count=0, successful_count=0, no_data_count=0, request_failed_count=0,
        validation_failed_count=0, insufficient_history_count=0, persisted_symbol_count=0,
        persisted_observation_count=0, required_sessions=required_sessions,
        requested_start=requested_start.isoformat(), requested_end=requested_end.isoformat(),
        constituents_sha256=constituents_hash, instrument_master_sha256=master_hash,
    )
    if report.mapped_count + report.unmapped_count != report.universe_count:
        raise RuntimeError("Mapping counts do not reconcile to eligible universe")

    save_run_start(report, db_path)
    save_mappings(resolved_run_id, mappings, db_path)
    for member in excluded:
        excluded_mapping = MappingRecord(member.symbol, "NSE", None, None, "EXCLUDED_PLACEHOLDER",
            "B3 rule: exclude DUMMY* placeholders", "Placeholder row excluded from scan universe", member.company_name,
            member.industry, member.series, member.isin)
        save_mappings(resolved_run_id, [excluded_mapping], db_path)
        excluded_result = SymbolResult(member.symbol, "EXCLUDED", "Placeholder excluded by B3 resolution")
        report.symbols.append(excluded_result.as_dict())
        save_symbol_result(resolved_run_id, excluded_result, db_path)

    last_request_at: float | None = None
    auth_abort_reason: str | None = None
    try:  # benchmark first: a failed benchmark fetch fails the run (design decision 6)
        raw_benchmark = provider.get_historical_data(
            report.benchmark_key, "1day",
            datetime.combine(requested_start, day_time.min, tzinfo=IST),
            datetime.combine(requested_end, day_time.min, tzinfo=IST))
        benchmark = _to_candles(raw_benchmark)
        benchmark_validation = validate_candles(benchmark, as_of=requested_end) if benchmark else None
        if not benchmark or benchmark_validation.status == "INVALID":
            detail = "no observations" if not benchmark else "; ".join(benchmark_validation.errors)
            report.benchmark_status = "FAILED"
            auth_abort_reason = f"Run stopped: benchmark {report.benchmark_key} invalid ({detail})"
        else:
            save_benchmark(report, benchmark, datetime.now(timezone.utc).isoformat(), db_path)
            report.benchmark_status, report.benchmark_observation_count = "OK", len(benchmark)
    except Exception as error:
        report.benchmark_status = "FAILED"
        auth_abort_reason = f"Run stopped: benchmark {report.benchmark_key} fetch failed ({type(error).__name__}: {error})"
    last_request_at = time.monotonic()
    for mapping in mappings:
        if mapping.mapping_status != "MAPPED":
            result = _failure(mapping)
            report.symbols.append(result.as_dict())
            save_symbol_result(resolved_run_id, result, db_path)
            continue
        if auth_abort_reason is not None:
            result = SymbolResult(mapping.symbol, "NOT_REQUESTED", auth_abort_reason, mapping.instrument_key)
            report.symbols.append(result.as_dict())
            save_symbol_result(resolved_run_id, result, db_path)
            continue
        report.requested_count += 1
        if last_request_at is not None:
            delay = pacing_seconds - (time.monotonic() - last_request_at)
            if delay > 0:
                sleeper(delay)
        last_request_at = time.monotonic()
        try:
            raw = provider.get_historical_data(
                mapping.instrument_key, "1day",
                datetime.combine(requested_start, day_time.min, tzinfo=IST),
                datetime.combine(requested_end, day_time.min, tzinfo=IST),
            )
        except AuthenticationError as error:
            result = SymbolResult(mapping.symbol, "REQUEST_FAILED", f"AuthenticationError: {error}", mapping.instrument_key,
                                  requested_start=requested_start.isoformat(), requested_end=requested_end.isoformat())
            report.request_failed_count += 1
            auth_abort_reason = "Run stopped after Upstox authentication failure (HTTP 401)"
            report.symbols.append(result.as_dict())
            save_symbol_result(resolved_run_id, result, db_path)
            continue
        except Exception as error:
            result = SymbolResult(mapping.symbol, "REQUEST_FAILED", f"{type(error).__name__}: {error}", mapping.instrument_key,
                                  requested_start=requested_start.isoformat(), requested_end=requested_end.isoformat())
            if mapping.series and mapping.series != "EQ":
                result.warnings.append(f"Constituent series {mapping.series}; daily history only, no intraday trading")
            report.request_failed_count += 1
            report.symbols.append(result.as_dict())
            save_symbol_result(resolved_run_id, result, db_path)
            continue
        candles = _to_candles(raw)
        retrieval_timestamp = datetime.now(timezone.utc).isoformat()
        result = SymbolResult(mapping.symbol, "NO_DATA" if not candles else "SUCCESS", None, mapping.instrument_key,
            len(candles), min((c.trading_date for c in candles if c.trading_date), default=None).isoformat() if candles else None,
            max((c.trading_date for c in candles if c.trading_date), default=None).isoformat() if candles else None,
            requested_start.isoformat(), requested_end.isoformat())
        if mapping.series and mapping.series != "EQ":
            result.warnings.append(f"Constituent series {mapping.series}; daily history only, no intraday trading")
        if not candles:
            report.no_data_count += 1
        else:
            validation = validate_candles(candles, as_of=requested_end)
            result.validation_status = validation.status
            result.warnings.extend(validation.warnings)
            if validation.status == "INVALID":
                result.status, result.reason = "VALIDATION_FAILED", "; ".join(validation.errors)
                report.validation_failed_count += 1
            elif len(candles) < required_sessions:
                result.status = "INSUFFICIENT_HISTORY"
                result.reason = f"{len(candles)} observations; {required_sessions} required"
                report.insufficient_history_count += 1
            else:
                selected = candles[-required_sessions:]
                result.status = "SUCCESS"
                result.observation_count = len(selected)
                result.first_date = selected[0].trading_date.isoformat()
                result.last_date = selected[-1].trading_date.isoformat()
                save_observations(report, result, selected, retrieval_timestamp, db_path)
                result.persisted_count = len(selected)
                report.successful_count += 1
                report.persisted_symbol_count += 1
                report.persisted_observation_count += len(selected)
        report.symbols.append(result.as_dict())
        save_symbol_result(resolved_run_id, result, db_path)

    report.run_completed_at = datetime.now(timezone.utc).isoformat()
    report.status = "FAILED" if auth_abort_reason else "COMPLETE"
    report.symbols.sort(key=lambda item: item["symbol"])
    finish_run(report, db_path)
    if report_dir is not None:
        write_report(report, report_dir)
    return report

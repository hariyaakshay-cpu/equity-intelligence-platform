from __future__ import annotations

import json
from dataclasses import asdict

from equity_intel.acquisition.models import AcquisitionReport, Candle, MappingRecord, SymbolResult
from equity_intel.persistence.connection import connect


def save_run_start(report: AcquisitionReport, db_path=None) -> None:
    connection = connect() if db_path is None else connect(db_path)
    try:
        connection.execute(
            "INSERT INTO acquisition_runs(run_id,run_started_at,status,report_json) VALUES(?,?,?,?)",
            (report.run_id, report.run_started_at, "RUNNING", json.dumps(report.as_dict(), sort_keys=True)),
        )
        connection.commit()
    finally:
        connection.close()


def save_mappings(run_id: str, records: list[MappingRecord], db_path=None) -> None:
    connection = connect() if db_path is None else connect(db_path)
    try:
        connection.executemany("""INSERT OR REPLACE INTO instrument_mappings
            (run_id,symbol,exchange,instrument_key,instrument_type,mapping_status,mapping_source,mapping_error,company_name,industry,series,isin)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", [
            (run_id, r.symbol, r.exchange, r.instrument_key, r.instrument_type, r.mapping_status, r.mapping_source,
             r.mapping_error, r.company_name, r.industry, r.series, r.isin) for r in records
        ])
        connection.commit()
    finally:
        connection.close()


def save_symbol_result(run_id: str, result: SymbolResult, db_path=None) -> None:
    connection = connect() if db_path is None else connect(db_path)
    try:
        connection.execute("""INSERT OR REPLACE INTO symbol_acquisition_results
            (run_id,symbol,status,reason,instrument_key,observation_count,first_date,last_date,requested_start,requested_end,validation_status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (run_id, result.symbol, result.status, result.reason, result.instrument_key,
            result.observation_count, result.first_date, result.last_date, result.requested_start, result.requested_end,
            result.validation_status))
        connection.commit()
    finally:
        connection.close()


def save_observations(report: AcquisitionReport, result: SymbolResult, candles: list[Candle], retrieval_timestamp: str, db_path=None) -> None:
    connection = connect() if db_path is None else connect(db_path)
    try:
        connection.executemany("""INSERT OR REPLACE INTO acquired_observations
            (run_id,symbol,trading_date,open,high,low,close,volume,source_vendor,source_endpoint,retrieval_timestamp,
             instrument_key,exchange,calendar_status,adjustment_status,data_version)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            (report.run_id, result.symbol, c.trading_date.isoformat(), c.open, c.high, c.low, c.close, c.volume,
             report.source_vendor, report.source_endpoint, retrieval_timestamp, result.instrument_key, "NSE",
             report.calendar_status, report.adjustment_status, report.run_id) for c in candles
        ])
        connection.commit()
    finally:
        connection.close()


def save_benchmark(report: AcquisitionReport, candles: list[Candle], retrieval_timestamp: str, db_path=None) -> None:
    connection = connect() if db_path is None else connect(db_path)
    try:
        connection.executemany("""INSERT OR REPLACE INTO acquired_benchmark
            (run_id,benchmark_key,trading_date,close,source_vendor,retrieval_timestamp) VALUES(?,?,?,?,?,?)""", [
            (report.run_id, report.benchmark_key, c.trading_date.isoformat(), c.close, report.source_vendor, retrieval_timestamp)
            for c in candles])
        connection.commit()
    finally:
        connection.close()


def finish_run(report: AcquisitionReport, db_path=None) -> None:
    connection = connect() if db_path is None else connect(db_path)
    try:
        connection.execute("UPDATE acquisition_runs SET run_completed_at=?,status=?,report_json=? WHERE run_id=?",
                           (report.run_completed_at, report.status, json.dumps(report.as_dict(), sort_keys=True), report.run_id))
        connection.commit()
    finally:
        connection.close()

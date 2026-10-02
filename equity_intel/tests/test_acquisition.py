from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from equity_intel.acquisition.mapping import map_constituents
from equity_intel.acquisition.models import Candle, Constituent, SymbolResult
from equity_intel.acquisition.persistence import save_observations
from equity_intel.acquisition.runner import run_equity_data_acquisition
from equity_intel.acquisition.universe import UniverseError, load_universe, normalize_symbol
from equity_intel.acquisition.validation import validate_candles
from core.providers.upstox_provider import AuthenticationError
import equity_intel.persistence.db_path_guard as db_path_guard
import equity_intel.persistence.connection as persistence_connection


def test_universe_normalizes_and_rejects_malformed_symbol():
    assert normalize_symbol("  rel-iance ") == "REL-IANCE"
    with pytest.raises(ValueError):
        normalize_symbol("bad symbol")


def test_universe_duplicate_symbol_is_not_silently_dropped(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text("Company Name,Industry,Symbol,Series,ISIN Code\nA,X,ABC,EQ,I1\nB,X,ABC,EQ,I2\n", encoding="utf-8")
    with pytest.raises(UniverseError, match="Duplicate"):
        load_universe(path)


def test_mapping_reports_success_ambiguous_unmapped_and_invalid():
    records = [
        Constituent("ABC", "A", "X", "EQ", "I1", 2),
        Constituent("MULTI", "M", "X", "EQ", "I2", 3),
        Constituent("NONE", "N", "X", "EQ", "I3", 4),
        Constituent("BAD", "B", "X", "EQ", "I4", 5),
    ]
    base = {"segment": "NSE_EQ", "exchange": "NSE", "instrument_type": "EQ"}
    instruments = [
        dict(base, isin="I1", trading_symbol="ABC", instrument_key="NSE_EQ|I1"),
        dict(base, isin="I2", trading_symbol="MULTI", instrument_key="NSE_EQ|I2A"),
        dict(base, isin="I2", trading_symbol="MULTI", instrument_key="NSE_EQ|I2B"),
        dict(base, isin="I4", trading_symbol="BAD", instrument_key="not-an-instrument-key"),
    ]
    results = map_constituents(records, instruments, "master.gz")
    assert [item.mapping_status for item in results] == ["MAPPED", "AMBIGUOUS", "UNMAPPED", "INVALID_INSTRUMENT"]


@pytest.mark.parametrize("candle, expected", [
    (Candle(date(2026, 1, 1), 2, 3, 1, 2.5, 10), "VALID"),
    (Candle(date(2026, 1, 1), 2, 1, 1, 2.5, 10), "INVALID"),
    (Candle(date(2026, 1, 1), 2, 3, 3.1, 2.5, 10), "INVALID"),
    (Candle(date(2026, 1, 1), 0, 3, 1, 2.5, 10), "INVALID"),
    (Candle(date(2026, 1, 1), 2, 3, 1, 2.5, None), "INVALID"),
    (Candle(date(2026, 1, 1), 2, 3, 1, 2.5, -2), "INVALID"),
])
def test_ohlcv_validation_rules(candle, expected):
    assert validate_candles([candle]).status == expected


def test_ohlcv_validation_detects_duplicate_unordered_future_and_zero_volume():
    a = Candle(date(2026, 1, 2), 2, 3, 1, 2.5, 0)
    b = Candle(date(2026, 1, 1), 2, 3, 1, 2.5, 1)
    result = validate_candles([a, a, b], as_of=date(2026, 1, 1))
    assert result.status == "INVALID"
    assert any("Duplicate" in error for error in result.errors)
    assert any("ascending" in error for error in result.errors)
    assert any("Future" in error for error in result.errors)
    assert result.warnings


def _fixtures(tmp_path: Path, symbols=("AAA", "BBB", "CCC")):
    csv_path = tmp_path / "universe.csv"
    csv_path.write_text("Company Name,Industry,Symbol,Series,ISIN Code\n" + "".join(
        f"{s},Industry,{s},EQ,ISIN-{s}\n" for s in symbols), encoding="utf-8")
    master_path = tmp_path / "master.json.gz"
    master = [{"segment": "NSE_EQ", "exchange": "NSE", "instrument_type": "EQ", "isin": f"ISIN-{s}",
               "trading_symbol": s, "instrument_key": f"NSE_EQ|ISIN-{s}"} for s in symbols]
    with gzip.open(master_path, "wt", encoding="utf-8") as stream:
        json.dump(master, stream)
    return csv_path, master_path


class FakeProvider:
    def __init__(self, fail=(), empty=(), bars=252):
        self.fail, self.empty, self.bars, self.calls = set(fail), set(empty), bars, []

    def get_historical_data(self, key, interval, start, end):
        symbol = key.split("|")[-1].replace("ISIN-", "")
        self.calls.append((key, interval, start, end))
        if symbol in self.fail:
            raise TimeoutError("fixture timeout")
        if symbol in self.empty:
            return []
        candles = []
        current = start.date()
        while len(candles) < self.bars and current <= end.date():
            if current.weekday() < 5:
                candles.append(SimpleNamespace(timestamp=datetime.combine(current, datetime.min.time()),
                    open=10.0, high=12.0, low=9.0, close=11.0, volume=100.0))
            current += timedelta(days=1)
        return candles


def test_acquisition_isolates_failures_persists_idempotently_and_reconciles(tmp_path, monkeypatch):
    csv_path, master_path = _fixtures(tmp_path)
    database = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    provider = FakeProvider(fail={"BBB"}, empty={"CCC"})
    report = run_equity_data_acquisition(provider, csv_path, master_path, start_date=date(2025, 1, 1),
        end_date=date(2026, 1, 1), run_id="fixed-run", required_sessions=252, pacing_seconds=0,
        db_path=database, report_dir=tmp_path / "reports")
    assert report.universe_count == report.mapped_count + report.unmapped_count == 3
    assert report.requested_count == report.successful_count + report.no_data_count + report.request_failed_count + report.validation_failed_count + report.insufficient_history_count
    assert (report.successful_count, report.no_data_count, report.request_failed_count) == (1, 1, 1)
    assert report.persisted_observation_count == 252
    assert (tmp_path / "reports/fixed-run.json").exists()
    saved = next(item for item in report.symbols if item["symbol"] == "AAA")
    same_run_retry = SymbolResult("AAA", "SUCCESS", instrument_key="NSE_EQ|ISIN-AAA",
        observation_count=1, first_date=saved["first_date"], last_date=saved["first_date"])
    save_observations(report, same_run_retry,
        [Candle(date.fromisoformat(saved["first_date"]), 10.0, 12.0, 9.0, 11.0, 100.0)],
        "2026-01-02T00:00:00+00:00", database)
    with persistence_connection.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM acquired_observations").fetchone()[0] == 252
        assert connection.execute("SELECT calendar_status FROM acquired_observations LIMIT 1").fetchone()[0] == "PROVISIONAL"
        assert connection.execute("SELECT COUNT(*) FROM symbol_acquisition_results").fetchone()[0] == 3


def test_insufficient_history_and_validation_failure_are_separate(tmp_path, monkeypatch):
    csv_path, master_path = _fixtures(tmp_path, ("SHORT", "BAD"))
    database = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    class Provider(FakeProvider):
        def get_historical_data(self, key, interval, start, end):
            result = super().get_historical_data(key, interval, start, end)
            if "BAD" in key:
                result[2].high = -1
            return result
    report = run_equity_data_acquisition(Provider(bars=4), csv_path, master_path, start_date=date(2025, 1, 1),
        end_date=date(2026, 1, 1), run_id="short-run", required_sessions=5, pacing_seconds=0, db_path=database)
    assert report.insufficient_history_count == 1
    assert report.validation_failed_count == 1


def test_authentication_failure_aborts_remaining_requests(tmp_path, monkeypatch):
    csv_path, master_path = _fixtures(tmp_path, ("AAA", "BBB"))
    database = tmp_path / "auth.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    class UnauthorizedProvider(FakeProvider):
        def get_historical_data(self, key, interval, start, end):
            self.calls.append((key, interval, start, end))
            raise AuthenticationError("Invalid Upstox API credentials")
    provider = UnauthorizedProvider()
    report = run_equity_data_acquisition(provider, csv_path, master_path, start_date=date(2025, 1, 1),
        end_date=date(2026, 1, 1), run_id="auth-run", pacing_seconds=0, db_path=database)
    assert report.status == "FAILED" and report.benchmark_status == "FAILED"
    assert report.requested_count == 0 and len(provider.calls) == 1  # only the benchmark was tried
    assert {item["status"] for item in report.symbols} == {"NOT_REQUESTED"}


def test_symbol_authentication_failure_after_good_benchmark_aborts_remaining_requests(tmp_path, monkeypatch):
    csv_path, master_path = _fixtures(tmp_path, ("AAA", "BBB"))
    database = tmp_path / "auth2.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    class Provider(FakeProvider):
        def get_historical_data(self, key, interval, start, end):
            if key.startswith("NSE_INDEX"):
                return super().get_historical_data(key, interval, start, end)
            self.calls.append((key, interval, start, end))
            raise AuthenticationError("Invalid Upstox API credentials")
    provider = Provider()
    report = run_equity_data_acquisition(provider, csv_path, master_path, start_date=date(2025, 1, 1),
        end_date=date(2026, 1, 1), run_id="auth2-run", pacing_seconds=0, db_path=database)
    assert report.status == "FAILED" and report.benchmark_status == "OK"
    assert report.requested_count == report.request_failed_count == 1
    assert {item["status"] for item in report.symbols} == {"REQUEST_FAILED", "NOT_REQUESTED"}


def test_benchmark_is_persisted_and_failed_benchmark_fails_the_run(tmp_path, monkeypatch):
    csv_path, master_path = _fixtures(tmp_path, ("AAA",))
    database = tmp_path / "bench.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    report = run_equity_data_acquisition(FakeProvider(), csv_path, master_path, start_date=date(2025, 1, 1),
        end_date=date(2026, 1, 1), run_id="ok-run", pacing_seconds=0, db_path=database)
    assert report.benchmark_status == "OK" and report.benchmark_observation_count > 0
    with persistence_connection.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM acquired_benchmark WHERE run_id='ok-run'").fetchone()[0] == report.benchmark_observation_count
    class NoBenchmark(FakeProvider):
        def get_historical_data(self, key, interval, start, end):
            return [] if key.startswith("NSE_INDEX") else super().get_historical_data(key, interval, start, end)
    failed = run_equity_data_acquisition(NoBenchmark(), csv_path, master_path, start_date=date(2025, 1, 1),
        end_date=date(2026, 1, 1), run_id="bad-run", pacing_seconds=0, db_path=database)
    assert failed.status == "FAILED" and failed.benchmark_status == "FAILED" and failed.requested_count == 0

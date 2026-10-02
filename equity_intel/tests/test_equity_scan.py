"""Integration tests for scripts/equity_scan.py.

No test touches the network or the real database: UpstoxProvider and
Settings are monkeypatched to a local fake, the instrument master is
monkeypatched to a fixed in-memory InstrumentMaster (no download), and
db_path_guard.CANONICAL_DB_PATH is monkeypatched to a tmp_path file for
every test (same pattern as the rest of equity_intel/tests).
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import equity_scan  # noqa: E402

from core.providers.base_provider import HistoricalCandle
from core.providers.upstox_provider import AuthenticationError, ProviderAPIError
from equity_intel.config import IST
from equity_intel.persistence import connection, db_path_guard
from equity_intel.scanner import scan_run
from equity_intel.config import AUTH_FAILURE_ABORT_THRESHOLD
from equity_intel.scanner.acquisition import AUTH_FAILED, AUTH_FAILURE
from equity_intel.scanner.corporate_actions import CORPORATE_ACTION_REVIEW_CSV_INVALID
from equity_intel.scanner.instrument_mapping import INSTRUMENT_MAP_EMPTY
from equity_intel.scanner.instrument_master import INSTRUMENT_MASTER_UNAVAILABLE, InstrumentMaster, InstrumentMasterUnavailableError
from equity_intel.scanner.trading_calendar import BENCHMARK_INSTRUMENT_KEY, CALENDAR_INVALID

_UNIVERSE_HEADER = "Company Name,Industry,Symbol,Series,ISIN Code\n"
_REVIEW_HEADER = "symbol,isin,event_type,effective_date,reason,reviewer,review_state\n"

_BENCHMARK_DATES = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]
_NOW = datetime(2026, 9, 26, 9, 0, 0, tzinfo=IST)  # the day after the last benchmark date


def _candle(date_str, close, volume=1000):
    ts = datetime.fromisoformat(date_str)
    return HistoricalCandle(timestamp=ts, open=close, high=close, low=close, close=close, volume=volume)


def _write_universe_csv(dir_path, rows):
    path = dir_path / "nifty500_constituents_2026-09-24.csv"
    path.write_text(_UNIVERSE_HEADER + "".join(rows), encoding="utf-8")
    return path


def _write_review_csv(dir_path, rows=()):
    path = dir_path / "corporate_action_review.csv"
    path.write_text(_REVIEW_HEADER + "".join(rows), encoding="utf-8")
    return path


def _default_master():
    return InstrumentMaster(
        rows=[
            {"segment": "NSE_EQ", "instrument_type": "EQ", "isin": "INE1", "instrument_key": "NSE_EQ|INE1"},
            {"segment": "NSE_EQ", "instrument_type": "EQ", "isin": "INE2", "instrument_key": "NSE_EQ|INE2"},
        ],
        source="test-source",
        fetched_at="2026-09-26T09:00:00+05:30",
        file_sha256="deadbeef",
        total_rows=2,
    )


class _FakeProvider:
    def __init__(self, *, benchmark_candles=None, symbol_candles=None, raise_on=None, raise_on_nth=None):
        self.benchmark_candles = benchmark_candles if benchmark_candles is not None else [
            _candle(d, close=100 + i) for i, d in enumerate(_BENCHMARK_DATES)
        ]
        self.symbol_candles = symbol_candles or {}
        self.raise_on = raise_on or {}
        # {(instrument_key, n): exc} -- raise only on the n-th (1-based) call for that key.
        self.raise_on_nth = raise_on_nth or {}
        self.calls = []

    def get_historical_data(self, instrument_key, interval, start_date, end_date):
        self.calls.append(instrument_key)
        nth = self.calls.count(instrument_key)
        if (instrument_key, nth) in self.raise_on_nth:
            raise self.raise_on_nth[(instrument_key, nth)]
        if instrument_key in self.raise_on:
            raise self.raise_on[instrument_key]
        if instrument_key == BENCHMARK_INSTRUMENT_KEY:
            return self.benchmark_candles
        return self.symbol_candles.get(instrument_key, [])


@pytest.fixture
def env(monkeypatch, tmp_path):
    db_path = tmp_path / "equity_intel.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", db_path)

    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    _write_universe_csv(
        reference_dir,
        [
            "Tata Consultancy Services,IT,TCS,EQ,INE1\n",
            "Infosys,IT,INFY,EQ,INE2\n",
        ],
    )
    _write_review_csv(reference_dir)

    monkeypatch.setattr(equity_scan, "DATA_REFERENCE_DIR", reference_dir)
    monkeypatch.setattr(equity_scan, "CORPORATE_ACTION_REVIEW_CSV", reference_dir / "corporate_action_review.csv")
    monkeypatch.setattr(equity_scan, "LOCK_PATH", tmp_path / "equity_intel_scan.lock")
    monkeypatch.setattr(equity_scan, "Settings", lambda: object())
    monkeypatch.setattr(equity_scan, "fetch_instrument_master", lambda *a, **k: _default_master())

    return reference_dir, db_path


def _install_provider(monkeypatch, provider):
    monkeypatch.setattr(equity_scan, "UpstoxProvider", lambda settings: provider)


def _scan_run_row(db_path, run_id):
    conn = connection.get_read_only_connection(db_path)
    row = conn.execute(
        "SELECT status, abort_reason, successful_symbols, failed_symbols, status_counts_json, universe_version, "
        "corporate_action_review_version FROM scan_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    conn.close()
    return row


def test_happy_path_completes_with_one_failed_and_one_insufficient_history_symbol(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider(
        symbol_candles={
            "NSE_EQ|INE1": [_candle(d, close=100 + i) for i, d in enumerate(_BENCHMARK_DATES)],  # TCS: 5 valid candles
        },
        raise_on={"NSE_EQ|INE2": ProviderAPIError("500 - server error")},  # INFY: fails
    )
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 0

    run_id = equity_scan.generate_run_id(_NOW)
    row = _scan_run_row(db_path, run_id)
    assert row[0] == "COMPLETE"
    assert row[2] == 1  # successful_symbols: TCS acquired (INSUFFICIENT_HISTORY, but not FAILED)
    assert row[3] == 1  # failed_symbols: INFY's acquisition errored
    assert row[5] is not None  # universe_version
    assert row[6] is not None  # corporate_action_review_version
    assert "INSUFFICIENT_HISTORY" in row[4]
    assert '"FAILED": 1' in row[4]


def test_acquisition_error_produces_a_failed_symbol_result(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider(raise_on={"NSE_EQ|INE2": ProviderAPIError("500 - server error")})
    _install_provider(monkeypatch, provider)

    equity_scan.run_scan(now=_NOW)

    conn = connection.get_read_only_connection(db_path)
    run_id = equity_scan.generate_run_id(_NOW)
    infy_row = conn.execute(
        "SELECT symbol_data_status, status_reason FROM symbol_scan_results WHERE scan_run_id = ? AND symbol = 'INFY'",
        (run_id,),
    ).fetchone()
    conn.close()
    assert infy_row[0] == "FAILED"
    assert "500" in infy_row[1]


def test_unmatched_isin_produces_failed_symbol_naming_the_isin(env, monkeypatch):
    reference_dir, db_path = env
    # Instrument master has no row at all for INE2 (INFY) -- only INE1 (TCS).
    monkeypatch.setattr(
        equity_scan,
        "fetch_instrument_master",
        lambda *a, **k: InstrumentMaster(
            rows=[{"segment": "NSE_EQ", "instrument_type": "EQ", "isin": "INE1", "instrument_key": "NSE_EQ|INE1"}],
            source="test",
            fetched_at="2026-09-26T09:00:00+05:30",
            file_sha256="deadbeef",
            total_rows=1,
        ),
    )
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)

    equity_scan.run_scan(now=_NOW)

    conn = connection.get_read_only_connection(db_path)
    run_id = equity_scan.generate_run_id(_NOW)
    infy_row = conn.execute(
        "SELECT symbol_data_status, status_reason FROM symbol_scan_results WHERE scan_run_id = ? AND symbol = 'INFY'",
        (run_id,),
    ).fetchone()
    conn.close()
    assert infy_row[0] == "FAILED"
    assert "INE2" in infy_row[1]
    # INFY was never even looked up for candles once its ISIN failed to map.
    assert "NSE_EQ|INE2" not in provider.calls


def test_calendar_invalid_aborts_the_run(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider(benchmark_candles=[])  # empty -> CalendarInvalidError
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1

    run_id = equity_scan.generate_run_id(_NOW)
    row = _scan_run_row(db_path, run_id)
    assert row[0] == "ABORTED"
    assert row[1] == CALENDAR_INVALID


def test_auth_failed_aborts_the_run(env, monkeypatch):
    reference_dir, db_path = env
    # Pre-flight (the 1st benchmark call) passes; the token then dies before
    # the calendar fetch (the 2nd benchmark call) -> AUTH_FAILED abort row.
    provider = _FakeProvider(raise_on_nth={(BENCHMARK_INSTRUMENT_KEY, 2): AuthenticationError("token expired")})
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1

    run_id = equity_scan.generate_run_id(_NOW)
    row = _scan_run_row(db_path, run_id)
    assert row[0] == "ABORTED"
    assert row[1] == AUTH_FAILED


def test_instrument_master_unavailable_aborts_the_run(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(
        equity_scan,
        "fetch_instrument_master",
        lambda *a, **k: (_ for _ in ()).throw(InstrumentMasterUnavailableError("download failed")),
    )

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1

    run_id = equity_scan.generate_run_id(_NOW)
    row = _scan_run_row(db_path, run_id)
    assert row[0] == "ABORTED"
    assert row[1] == INSTRUMENT_MASTER_UNAVAILABLE


def test_instrument_map_empty_aborts_the_run(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)
    monkeypatch.setattr(
        equity_scan,
        "fetch_instrument_master",
        lambda *a, **k: InstrumentMaster(
            rows=[{"segment": "NSE_EQ", "instrument_type": "EQ", "isin": "SOME_OTHER_ISIN", "instrument_key": "X"}],
            source="test",
            fetched_at="2026-09-26T09:00:00+05:30",
            file_sha256="deadbeef",
            total_rows=1,
        ),
    )

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1

    run_id = equity_scan.generate_run_id(_NOW)
    row = _scan_run_row(db_path, run_id)
    assert row[0] == "ABORTED"
    assert row[1] == INSTRUMENT_MAP_EMPTY


def test_corporate_action_review_csv_invalid_aborts_the_run(env, monkeypatch):
    reference_dir, db_path = env
    monkeypatch.setattr(equity_scan, "CORPORATE_ACTION_REVIEW_CSV", reference_dir / "does_not_exist.csv")
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1

    run_id = equity_scan.generate_run_id(_NOW)
    row = _scan_run_row(db_path, run_id)
    assert row[0] == "ABORTED"
    assert row[1] == CORPORATE_ACTION_REVIEW_CSV_INVALID


def test_interrupted_marks_a_leftover_running_row_from_a_previous_process(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)

    # Simulate a previous process that died mid-scan: a RUNNING row with no
    # finished_at, inserted directly (not via start_scan_run, so it isn't
    # "this" run).
    from equity_intel.persistence import connection

    conn = connection.get_connection(db_path)
    connection.initialize_schema(conn)
    conn.execute(
        "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
        "VALUES ('stale_run', '2026-09-25T09:00:00+05:30', 'RUNNING', 'BLOCKED_B2')"
    )
    conn.commit()
    conn.close()

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 0

    stale_row = _scan_run_row(db_path, "stale_run")
    assert stale_row[0] == "ABORTED"
    assert stale_row[1] == scan_run.INTERRUPTED

    new_row = _scan_run_row(db_path, equity_scan.generate_run_id(_NOW))
    assert new_row[0] == "COMPLETE"


def test_a_symbol_whose_candle_breaks_storage_is_isolated_as_failed(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider(
        symbol_candles={
            # TCS: a close that cannot be Decimal-quantized -- raises
            # decimal.InvalidOperation inside validate_candle/write_snapshot.
            "NSE_EQ|INE1": [
                HistoricalCandle(
                    timestamp=datetime.fromisoformat(_BENCHMARK_DATES[0]),
                    open="NOT_A_NUMBER",
                    high="NOT_A_NUMBER",
                    low="NOT_A_NUMBER",
                    close="NOT_A_NUMBER",
                    volume=1000,
                )
            ],
            # INFY: perfectly normal candles, must still be processed.
            "NSE_EQ|INE2": [_candle(d, close=100 + i) for i, d in enumerate(_BENCHMARK_DATES)],
        }
    )
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 0  # the run still COMPLETEs

    run_id = equity_scan.generate_run_id(_NOW)
    conn = connection.get_read_only_connection(db_path)
    tcs_row = conn.execute(
        "SELECT symbol_data_status, status_reason FROM symbol_scan_results WHERE scan_run_id = ? AND symbol = 'TCS'",
        (run_id,),
    ).fetchone()
    infy_row = conn.execute(
        "SELECT symbol_data_status FROM symbol_scan_results WHERE scan_run_id = ? AND symbol = 'INFY'",
        (run_id,),
    ).fetchone()
    # TCS's broken candle was never committed as a snapshot -- rolled back.
    tcs_snapshot_count = conn.execute(
        "SELECT COUNT(*) FROM price_fetch_snapshots WHERE scan_run_id = ? AND symbol = 'TCS'", (run_id,)
    ).fetchone()[0]
    conn.close()

    assert tcs_row[0] == "FAILED"
    assert tcs_row[1]  # some exception message was recorded
    assert tcs_snapshot_count == 0
    assert infy_row[0] in ("INSUFFICIENT_HISTORY", "STALE", "VALID")  # INFY still processed normally

    row = _scan_run_row(db_path, run_id)
    assert row[0] == "COMPLETE"
    assert row[3] == 1  # failed_symbols: just TCS
    assert row[2] == 1  # successful_symbols: just INFY


def test_symbols_filter_with_zero_universe_matches_exits_before_creating_a_scan_run(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(symbols_filter={"NOT_A_REAL_SYMBOL"}, now=_NOW)
    assert exit_code == 1
    assert provider.calls == []  # never even started fetching anything

    # No scan_runs row at all -- the database wasn't even initialized.
    if db_path.exists():
        conn = connection.get_read_only_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        conn.close()
        assert count == 0


def test_lock_file_refuses_a_concurrent_run_and_never_touches_scan_runs(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)

    # Simulate an actually-running second process: a RUNNING scan_runs row
    # (as a live process would have) plus the lock file it's holding.
    conn = connection.get_connection(db_path)
    connection.initialize_schema(conn)
    conn.execute(
        "INSERT INTO scan_runs (run_id, started_at, status, scoring_status) "
        "VALUES ('live_run', '2026-09-26T08:59:00+05:30', 'RUNNING', 'BLOCKED_B2')"
    )
    conn.commit()
    conn.close()
    equity_scan.LOCK_PATH.write_text('{"pid": 999999, "started_at": "2026-09-26T08:59:00+05:30"}', encoding="utf-8")

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1
    assert provider.calls == []  # refused before ever touching the provider

    # The genuinely-live run's row must still say RUNNING -- never marked
    # INTERRUPTED just because a second invocation was attempted.
    live_row = _scan_run_row(db_path, "live_run")
    assert live_row[0] == "RUNNING"

    # The lock file is untouched (still the "other process"'s contents).
    assert "999999" in equity_scan.LOCK_PATH.read_text(encoding="utf-8")


def test_lock_file_is_removed_after_a_completed_run(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)

    equity_scan.run_scan(now=_NOW)
    assert not equity_scan.LOCK_PATH.exists()


def test_lock_file_is_removed_after_an_aborted_run(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider(benchmark_candles=[])  # -> CALENDAR_INVALID abort
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1
    assert not equity_scan.LOCK_PATH.exists()


def test_symbols_filter_only_scans_the_requested_symbols(env, monkeypatch):
    reference_dir, db_path = env
    provider = _FakeProvider()
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(symbols_filter={"TCS"}, now=_NOW)
    assert exit_code == 0

    conn = connection.get_read_only_connection(db_path)
    run_id = equity_scan.generate_run_id(_NOW)
    symbols = {
        row[0]
        for row in conn.execute(
            "SELECT symbol FROM symbol_scan_results WHERE scan_run_id = ?", (run_id,)
        ).fetchall()
    }
    conn.close()
    assert symbols == {"TCS"}


# --- pre-flight token check -------------------------------------------------

_SECRET = "SECRET-TOKEN-abc123"


def _assert_no_scan_run_row(db_path):
    if db_path.exists():
        conn = connection.get_read_only_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        conn.close()
        assert count == 0


def test_preflight_auth_failure_creates_no_scan_run_row(env, monkeypatch, capsys):
    reference_dir, db_path = env
    monkeypatch.setattr(equity_scan, "Settings", lambda: type("S", (), {"UPSTOX_ACCESS_TOKEN": _SECRET})())
    provider = _FakeProvider(raise_on={BENCHMARK_INSTRUMENT_KEY: AuthenticationError("Invalid Upstox API credentials")})
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)

    assert exit_code == 1
    assert provider.calls == [BENCHMARK_INSTRUMENT_KEY]  # only the probe; nothing else fetched
    _assert_no_scan_run_row(db_path)
    out = capsys.readouterr()
    assert "Pre-flight failed" in out.out
    assert _SECRET not in out.out + out.err
    assert not equity_scan.LOCK_PATH.exists()


def test_preflight_non_auth_failure_creates_no_row_and_redacts_the_token(env, monkeypatch, capsys):
    reference_dir, db_path = env
    monkeypatch.setattr(equity_scan, "Settings", lambda: type("S", (), {"UPSTOX_ACCESS_TOKEN": _SECRET})())
    provider = _FakeProvider(raise_on={BENCHMARK_INSTRUMENT_KEY: ProviderAPIError(f"503 - upstream said {_SECRET}")})
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)

    assert exit_code == 1
    _assert_no_scan_run_row(db_path)
    out = capsys.readouterr()
    assert "Pre-flight failed" in out.out
    assert "503" in out.out
    assert _SECRET not in out.out + out.err


def test_preflight_provider_construction_failure_creates_no_row(env, monkeypatch, capsys):
    reference_dir, db_path = env

    def _boom(settings):
        raise ValueError("UPSTOX_ACCESS_TOKEN is required in settings to use UpstoxProvider")

    monkeypatch.setattr(equity_scan, "UpstoxProvider", _boom)

    exit_code = equity_scan.run_scan(now=_NOW)

    assert exit_code == 1
    _assert_no_scan_run_row(db_path)
    assert "Pre-flight failed" in capsys.readouterr().out


# --- top-level abort handling ----------------------------------------------


def _raise(exc):
    def _thrower(*a, **k):
        raise exc

    return _thrower


def test_unexpected_exception_outside_the_loop_marks_the_run_aborted_and_reraises(env, monkeypatch):
    reference_dir, db_path = env
    _install_provider(monkeypatch, _FakeProvider())
    monkeypatch.setattr(equity_scan, "map_universe_isins", _raise(RuntimeError("boom outside loop")))

    with pytest.raises(RuntimeError, match="boom outside loop"):
        equity_scan.run_scan(now=_NOW)

    conn = connection.get_read_only_connection(db_path)
    row = conn.execute(
        "SELECT status, abort_reason, errors_json, finished_at FROM scan_runs WHERE run_id = ?",
        (equity_scan.generate_run_id(_NOW),),
    ).fetchone()
    conn.close()
    assert row[0] == "ABORTED"  # not stuck RUNNING
    assert row[1] == scan_run.UNEXPECTED_ERROR
    assert "RuntimeError" in row[2] and "boom outside loop" in row[2]
    assert row[3] is not None
    assert not equity_scan.LOCK_PATH.exists()


def test_error_summary_is_truncated(env, monkeypatch):
    reference_dir, db_path = env
    _install_provider(monkeypatch, _FakeProvider())
    monkeypatch.setattr(equity_scan, "map_universe_isins", _raise(RuntimeError("x" * 5000)))

    with pytest.raises(RuntimeError):
        equity_scan.run_scan(now=_NOW)

    conn = connection.get_read_only_connection(db_path)
    errors_json = conn.execute("SELECT errors_json FROM scan_runs").fetchone()[0]
    conn.close()
    assert len(errors_json) < 700


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_keyboard_interrupt_and_system_exit_mark_the_run_interrupted(env, monkeypatch, exc_type):
    reference_dir, db_path = env
    _install_provider(monkeypatch, _FakeProvider())
    monkeypatch.setattr(equity_scan, "map_universe_isins", _raise(exc_type()))

    with pytest.raises(exc_type):
        equity_scan.run_scan(now=_NOW)

    row = _scan_run_row(db_path, equity_scan.generate_run_id(_NOW))
    assert row[0] == "ABORTED"
    assert row[1] == scan_run.INTERRUPTED
    assert not equity_scan.LOCK_PATH.exists()


def test_a_failing_abort_write_does_not_mask_the_original_exception(env, monkeypatch, capsys):
    reference_dir, db_path = env
    _install_provider(monkeypatch, _FakeProvider())
    monkeypatch.setattr(equity_scan, "map_universe_isins", _raise(RuntimeError("original error")))
    monkeypatch.setattr(scan_run, "abort_scan_run_if_running", _raise(sqlite3.OperationalError("database is locked")))

    with pytest.raises(RuntimeError, match="original error"):  # not the sqlite error
        equity_scan.run_scan(now=_NOW)

    assert "could not be marked ABORTED" in capsys.readouterr().err
    # Left RUNNING, but the next scan start recovers it as INTERRUPTED.
    assert _scan_run_row(db_path, equity_scan.generate_run_id(_NOW))[0] == "RUNNING"
    assert not equity_scan.LOCK_PATH.exists()


def test_abort_write_on_an_already_finished_run_is_a_no_op(env):
    reference_dir, db_path = env
    conn = connection.get_connection(db_path)
    connection.initialize_schema(conn)
    scan_run.start_scan_run(conn, run_id="r1", requested_symbols=1, now=_NOW)
    scan_run.abort_scan_run(conn, run_id="r1", abort_reason=CALENDAR_INVALID, now=_NOW)
    assert scan_run.abort_scan_run_if_running(conn, run_id="r1", abort_reason=scan_run.UNEXPECTED_ERROR, now=_NOW) is False
    conn.close()
    assert _scan_run_row(db_path, "r1")[1] == CALENDAR_INVALID  # original reason preserved


# --- auth circuit breaker ---------------------------------------------------


def _use_n_symbol_universe(reference_dir, monkeypatch, n):
    _write_universe_csv(reference_dir, [f"Co {i},IT,SYM{i},EQ,INE{i}\n" for i in range(1, n + 1)])
    monkeypatch.setattr(
        equity_scan,
        "fetch_instrument_master",
        lambda *a, **k: InstrumentMaster(
            rows=[
                {"segment": "NSE_EQ", "instrument_type": "EQ", "isin": f"INE{i}", "instrument_key": f"NSE_EQ|INE{i}"}
                for i in range(1, n + 1)
            ],
            source="test",
            fetched_at="2026-09-26T09:00:00+05:30",
            file_sha256="deadbeef",
            total_rows=n,
        ),
    )


def test_auth_circuit_breaker_trips_at_n_and_stops_fetching(env, monkeypatch):
    reference_dir, db_path = env
    n = AUTH_FAILURE_ABORT_THRESHOLD
    _use_n_symbol_universe(reference_dir, monkeypatch, n + 3)
    provider = _FakeProvider(
        raise_on={f"NSE_EQ|INE{i}": AuthenticationError("token expired") for i in range(1, n + 4)}
    )
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 1

    symbol_calls = [c for c in provider.calls if c != BENCHMARK_INSTRUMENT_KEY]
    assert len(symbol_calls) == n  # stopped fetching at the N-th consecutive failure

    run_id = equity_scan.generate_run_id(_NOW)
    row = _scan_run_row(db_path, run_id)
    assert row[0] == "ABORTED"
    assert row[1] == AUTH_FAILURE

    conn = connection.get_read_only_connection(db_path)
    failed = conn.execute(
        "SELECT COUNT(*) FROM symbol_scan_results WHERE scan_run_id = ? AND symbol_data_status = 'FAILED'", (run_id,)
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM symbol_scan_results WHERE scan_run_id = ?", (run_id,)).fetchone()[0]
    conn.close()
    assert failed == n - 1  # the tripping symbol itself is not recorded
    assert total == n - 1  # the remaining symbols were NOT marked FAILED one by one


def test_auth_circuit_breaker_resets_on_a_non_auth_outcome(env, monkeypatch):
    reference_dir, db_path = env
    n = AUTH_FAILURE_ABORT_THRESHOLD
    # (n-1) auth failures, one non-auth outcome, (n-1) auth failures: never n in a row.
    total_symbols = 2 * (n - 1) + 1
    _use_n_symbol_universe(reference_dir, monkeypatch, total_symbols)
    auth = AuthenticationError("token expired")
    raise_on = {f"NSE_EQ|INE{i}": auth for i in range(1, total_symbols + 1) if i != n}
    provider = _FakeProvider(raise_on=raise_on)  # INE<n> returns normally
    _install_provider(monkeypatch, provider)

    exit_code = equity_scan.run_scan(now=_NOW)
    assert exit_code == 0

    row = _scan_run_row(db_path, equity_scan.generate_run_id(_NOW))
    assert row[0] == "COMPLETE"
    assert row[3] == total_symbols - 1  # every auth-failed symbol recorded FAILED

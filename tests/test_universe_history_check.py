"""Offline tests for scripts/universe_history_check.py (no network, no database)."""
import ast
import builtins
import csv
import importlib.util
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.providers.upstox_provider import AuthenticationError, ProviderAPIError
from equity_intel.config import IST
from equity_intel.persistence.db_path_guard import assert_allowed_db_path
from equity_intel.scanner.execution_guard import FORBIDDEN_PREFIXES

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "universe_history_check.py"
_spec = importlib.util.spec_from_file_location("universe_history_check", SCRIPT)
uhc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uhc)

FORBIDDEN_DB_NAMES = ("equity_intel.db", "oms_state.db", "oms_shadow.db", "production_trading.db")


def candle(d, volume=100):
    return SimpleNamespace(timestamp=datetime(d.year, d.month, d.day, tzinfo=IST), volume=volume)


class FakeLimiter:
    def wait(self):
        pass


class FakeProvider:
    """get_historical_data(key, interval, start, end) -> candles whose date is in [start, end]."""

    def __init__(self, data=None, errors=None):
        self.data = data or {}
        self.errors = errors or {}
        self.calls = []

    def get_historical_data(self, key, interval, start, end):
        self.calls.append((key, interval, start.date(), end.date()))
        if key in self.errors:
            raise self.errors[key]
        return [c for c in self.data.get(key, []) if start.date() <= uhc._candle_date(c) <= end.date()]


SESSIONS = [date(2026, 9, 28) + timedelta(days=i) for i in range(5)]  # Mon-Fri
TODAY = date(2026, 10, 2)


def run(provider, selection, clock=None):
    kwargs = {"clock": clock} if clock else {}
    return uhc.check_symbols(provider, selection, SESSIONS, TODAY, FakeLimiter(), **kwargs)


def test_summarize_counts_gaps_and_zero_volume():
    candles = [candle(SESSIONS[0]), candle(SESSIONS[1], volume=0), candle(SESSIONS[3], volume=None)]
    facts = uhc.summarize(candles, SESSIONS)
    assert facts["first_bar"] == SESSIONS[0] and facts["last_bar"] == SESSIONS[3]
    assert facts["bars"] == 3
    assert facts["gap_count"] == 1  # SESSIONS[2]
    assert facts["zero_volume_bars"] == 2


def test_summarize_counts_bar_on_non_session_date_without_calling_it_a_gap():
    sessions = [date(2026, 9, 25), date(2026, 9, 28)]
    facts = uhc.summarize([candle(date(2026, 9, 25)), candle(date(2026, 9, 26)), candle(date(2026, 9, 28))], sessions)
    assert facts["gap_count"] == 0 and facts["non_session_bars"] == 1


def test_no_data_symbol():
    rows, results, aborted = run(FakeProvider(), [("AAA", "NSE_EQ|INE000A01010")])
    assert aborted is None
    assert rows[0]["status"] == uhc.STATUS_NO_DATA and rows[0]["bars"] == 0 and rows[0]["gap_count"] is None


def test_error_symbol_does_not_abort_run_and_is_recorded():
    provider = FakeProvider(
        data={"NSE_EQ|INE000B01010": [candle(SESSIONS[0])]},
        errors={"NSE_EQ|INE000A01010": ProviderAPIError("Upstox API returned HTTP 400")},
    )
    rows, _, aborted = run(provider, [("AAA", "NSE_EQ|INE000A01010"), ("BBB", "NSE_EQ|INE000B01010")])
    assert aborted is None
    assert rows[0]["status"] == uhc.STATUS_ERROR and "HTTP 400" in rows[0]["error"]
    assert rows[1]["status"] == uhc.STATUS_DATA and rows[1]["bars"] == 1


def test_auth_failure_aborts_run():
    provider = FakeProvider(errors={"NSE_EQ|INE000A01010": AuthenticationError("Invalid Upstox API credentials")})
    rows, _, aborted = run(provider, [("AAA", "NSE_EQ|INE000A01010"), ("BBB", "NSE_EQ|INE000B01010")])
    assert aborted.startswith("AUTH_FAILED") and rows == []
    assert all(call[0] == "NSE_EQ|INE000A01010" for call in provider.calls)


def test_duplicate_keys_share_one_fetch():
    key = "NSE_EQ|INE000A01010"
    provider = FakeProvider(data={key: [candle(SESSIONS[0])]})
    rows, results, _ = run(provider, [("AAA", key), ("AAA", key)])
    assert len(rows) == 2 and len(results) == 1
    assert len(provider.calls) == uhc.MAX_WINDOWS
    assert rows[0]["bars"] == rows[1]["bars"] == 1


def test_windows_are_daily_decade_or_shorter_and_floor_bounded():
    provider = FakeProvider()
    run(provider, [("AAA", "NSE_EQ|INE000A01010")])
    assert len(provider.calls) == uhc.MAX_WINDOWS
    for _, interval, start, end in provider.calls:
        assert interval == "1day" and (end - start).days <= uhc.WINDOW_DAYS and start >= uhc.HISTORY_FLOOR
    assert provider.calls[0][3] == TODAY
    assert min(c[2] for c in provider.calls) == uhc.HISTORY_FLOOR


def test_empty_latest_window_still_reaches_older_history():
    old = date(2010, 6, 1)
    key = "NSE_EQ|INE000A01010"
    rows, _, _ = run(FakeProvider(data={key: [candle(old)]}), [("AAA", key)])
    assert rows[0]["status"] == uhc.STATUS_DATA and rows[0]["first_bar"] == old


def test_per_symbol_deadline_marks_error():
    ticks = iter(range(0, 1000, 100))
    rows, _, aborted = run(FakeProvider(), [("AAA", "NSE_EQ|INE000A01010")], clock=lambda: next(ticks))
    assert aborted is None and rows[0]["status"] == uhc.STATUS_ERROR and "deadline" in rows[0]["error"]


def _write_symbols(path, n, status="RESOLVED", key_for=lambda i: f"NSE_EQ|INE{i:06d}01010"):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "vendor_status", "instrument_key"])
        w.writeheader()
        for i in range(n):
            w.writerow({"symbol": f"S{i}", "vendor_status": status, "instrument_key": key_for(i)})


def test_load_selection_filters_resolved_only(tmp_path):
    p = tmp_path / "m.csv"
    _write_symbols(p, 3)
    with open(p, "a", newline="", encoding="utf-8") as fh:
        fh.write("OTHER,IN_DATASET,NSE_EQ|INE9\n")
    assert [s for s, _ in uhc.load_selection(p)] == ["S0", "S1", "S2"]


def test_load_selection_enforces_cap(tmp_path):
    p = tmp_path / "m.csv"
    _write_symbols(p, uhc.MAX_SYMBOLS + 1)
    with pytest.raises(ValueError, match="hard cap"):
        uhc.load_selection(p)


def test_load_selection_rejects_ambiguous_mapping(tmp_path):
    p = tmp_path / "m.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        fh.write("symbol,vendor_status,instrument_key\nAAA,RESOLVED,NSE_EQ|INE1\nAAA,RESOLVED,NSE_EQ|INE2\n")
    with pytest.raises(ValueError, match="ambiguous"):
        uhc.load_selection(p)


def test_write_outputs_refuses_other_dir_and_existing_files(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="outputs must go to"):
        uhc.write_outputs(tmp_path, [], {})
    monkeypatch.setattr(uhc, "OUTPUT_DIR", tmp_path)
    uhc.write_outputs(tmp_path, [], {"k": 1})
    with pytest.raises(FileExistsError):
        uhc.write_outputs(tmp_path, [], {"k": 1})


def test_csv_columns_and_run_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(uhc, "OUTPUT_DIR", tmp_path)
    key = "NSE_EQ|INE000A01010"
    symbols = tmp_path / "m.csv"
    _write_symbols(symbols, 1, key_for=lambda i: key)
    selection = uhc.load_selection(symbols) * 2  # duplicate row, same key
    rows, results, aborted = run(FakeProvider(data={key: [candle(SESSIONS[0])]}), selection)
    meta = uhc.build_meta(started=datetime(2026, 10, 3), finished=datetime(2026, 10, 3), today=TODAY,
                          selection=selection, rows=rows, results=results, aborted=aborted,
                          symbols_csv=symbols, sessions=SESSIONS)
    uhc.write_outputs(tmp_path, rows, meta)
    with open(tmp_path / uhc.CSV_NAME, newline="", encoding="utf-8") as fh:
        read = list(csv.DictReader(fh))
    assert list(read[0].keys()) == uhc.CSV_FIELDS and len(read) == 2
    saved = json.loads((tmp_path / uhc.RUN_JSON_NAME).read_text(encoding="utf-8"))
    assert saved["rows"] == 2 and saved["unique_keys"] == 1
    assert saved["calendar"]["sha256"] == uhc.sha256_file(uhc.CALENDAR_PATH)
    assert "2020-01-07" in saved["calendar"]["note"] and "Nifty 500" in saved["calendar"]["note"]
    assert saved["symbols_csv"]["sha256"] == uhc.sha256_file(symbols)


def test_run_touches_no_database_path(tmp_path, monkeypatch):
    """Fails if any sqlite connection is attempted or any forbidden DB path is opened."""
    touched = []
    real_open = builtins.open

    def spy_open(file, *a, **kw):
        if any(name in str(file) for name in FORBIDDEN_DB_NAMES):
            touched.append(str(file))
        return real_open(file, *a, **kw)

    def spy_connect(*a, **kw):
        touched.append(f"sqlite3.connect{a}")
        raise AssertionError("sqlite3.connect called")

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(sqlite3, "connect", spy_connect)
    monkeypatch.setattr(uhc, "OUTPUT_DIR", tmp_path)
    key = "NSE_EQ|INE000A01010"
    symbols = tmp_path / "m.csv"
    _write_symbols(symbols, 1, key_for=lambda i: key)
    selection = uhc.load_selection(symbols)
    rows, results, aborted = run(FakeProvider(data={key: [candle(SESSIONS[0])]}), selection)
    meta = uhc.build_meta(started=datetime(2026, 10, 3), finished=datetime(2026, 10, 3), today=TODAY,
                          selection=selection, rows=rows, results=results, aborted=aborted,
                          symbols_csv=symbols, sessions=SESSIONS)
    uhc.write_outputs(tmp_path, rows, meta)
    assert touched == []


@pytest.mark.parametrize("name", FORBIDDEN_DB_NAMES)
def test_forbidden_db_paths_are_refused_by_the_185e272_guard(name):
    candidates = [uhc.OUTPUT_DIR / name]
    if name != "equity_intel.db":  # data/equity_intel.db is the one path the guard allows
        candidates.append(Path(uhc.REPO_ROOT) / "data" / name)
    for candidate in candidates:
        with pytest.raises(ValueError):
            assert_allowed_db_path(candidate)


def test_script_has_no_db_or_trading_imports():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in imported:
        assert name.split(".")[0] not in {"sqlite3", "sqlalchemy"}
        assert not name.startswith("equity_intel.persistence") and name != "equity_intel.scanner.db"
        for forbidden in FORBIDDEN_PREFIXES:
            assert not (name == forbidden or name.startswith(forbidden + ".")), name
    src = SCRIPT.read_text(encoding="utf-8")
    for db in FORBIDDEN_DB_NAMES:
        assert db not in src.replace("FORBIDDEN", "")


def test_load_token_from_env_file_ignores_other_keys_and_cwd_env(tmp_path, monkeypatch):
    env = tmp_path / "t.env"
    env.write_text("UPSTOX_ACCESS_TOKEN=TOK-FILE\nUPSTOX_API_SECRET=OTHER-SECRET\n", encoding="utf-8")
    (tmp_path / ".env").write_text("UPSTOX_ACCESS_TOKEN=TOK-CWD\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "TOK-PROCESS")
    assert uhc.load_token(env).UPSTOX_ACCESS_TOKEN == "TOK-FILE"
    assert uhc.load_token(None).UPSTOX_ACCESS_TOKEN == "TOK-PROCESS"  # not the cwd .env
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN")
    with pytest.raises(ValueError, match="process environment") as exc:
        uhc.load_token(None)  # cwd .env holds TOK-CWD but must not be read
    assert "TOK-CWD" not in str(exc.value)


def test_token_never_appears_in_errors_or_repr(tmp_path):
    env = tmp_path / "t.env"
    env.write_text("UPSTOX_ACCESS_TOKEN=TOK-SECRET\nUPSTOX_API_SECRET=OTHER-SECRET\n", encoding="utf-8")
    text = repr(uhc.load_token(env)) + str(uhc.load_token(env))
    for bad in (tmp_path / "missing.env", tmp_path):
        with pytest.raises(ValueError) as exc:
            uhc.load_token(bad)
        text += str(exc.value)
    empty = tmp_path / "empty.env"
    empty.write_text("OTHER=OTHER-SECRET\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        uhc.load_token(empty)
    text += str(exc.value)
    assert "TOK-SECRET" not in text and "OTHER-SECRET" not in text


def test_main_prints_nothing_secret_and_builds_provider_from_token_only(tmp_path, monkeypatch, capsys):
    env = tmp_path / "t.env"
    env.write_text("UPSTOX_ACCESS_TOKEN=TOK-SECRET\nUPSTOX_API_SECRET=OTHER-SECRET\n", encoding="utf-8")
    symbols = tmp_path / "m.csv"
    _write_symbols(symbols, 1)
    monkeypatch.setattr(uhc, "OUTPUT_DIR", tmp_path / "out")
    seen = {}

    class StubProvider(FakeProvider):
        def __init__(self, settings):
            super().__init__()
            seen["settings"] = settings

    monkeypatch.setattr(uhc, "UpstoxProvider", StubProvider)
    monkeypatch.setattr(uhc, "MAX_SYMBOLS", 90)
    uhc.main(["--symbols-csv", str(symbols), "--env-file", str(env)])
    out = capsys.readouterr()
    assert seen["settings"].UPSTOX_ACCESS_TOKEN == "TOK-SECRET"
    assert "TOK-SECRET" not in out.out + out.err and "OTHER-SECRET" not in out.out + out.err
    for f in (tmp_path / "out").iterdir():
        assert "TOK-SECRET" not in f.read_text(encoding="utf-8")

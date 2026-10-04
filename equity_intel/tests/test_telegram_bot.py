"""Tests for telegram_bot/: digest text and sender. No network, no real DB."""
import pytest
import requests

from dashboard import queries
from equity_intel.persistence import connection, db_path_guard
from scripts.dashboard_demo_seed import seed_demo_database
from telegram_bot import digest, sender


@pytest.fixture
def demo_conn(monkeypatch, tmp_path):
    demo = tmp_path / "equity_intel_demo.db"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", tmp_path / "equity_intel.db")
    monkeypatch.setattr(db_path_guard, "DEMO_DB_PATH", demo)
    seed_demo_database(demo)
    conn = connection.get_read_only_connection(demo)
    yield conn
    conn.close()


def test_digest_without_e4_scan_says_breadth_unavailable(demo_conn):
    text = digest.build_digest(demo_conn)
    assert "latest closed session" in text
    assert "breadth unavailable" in text
    assert digest.DISCLAIMER in text
    assert len(text) <= digest.TELEGRAM_MAX_CHARS


def test_digest_with_no_runs_is_a_plain_notice():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE scan_runs (run_id TEXT, status TEXT, symbols_filter_json TEXT, started_at TEXT)")
    text = digest.build_digest(conn)
    conn.close()
    assert "No completed scan run" in text and digest.DISCLAIMER in text


def test_digest_breadth_and_near_high(demo_conn, monkeypatch):
    monkeypatch.setattr(queries, "get_latest_e4_scan", lambda c: {
        "scan_id": "e4", "acquisition_run_id": "acq", "asof_date": "2000-01-01"})
    monkeypatch.setattr(queries, "get_candidates", lambda c, rid, **kw: (3, [
        {"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}]))
    monkeypatch.setattr(queries, "get_e4_features", lambda c, sid, syms, acq=None: {
        "AAA": {"close": 110, "ema_long": 100, "ema_medium": 100, "ema_short": 100, "roc": 1.0, "distance_from_high": 0.5},
        "BBB": {"close": 90, "ema_long": 100, "ema_medium": 100, "ema_short": 100, "roc": -1.0, "distance_from_high": 9.0},
        "CCC": {"close": None, "ema_long": None, "ema_medium": None, "ema_short": None, "roc": None, "distance_from_high": None},
    })
    text = digest.build_digest(demo_conn)
    assert "Above EMA 200: 1 of 2 (50.0%)" in text
    assert "Positive ROC: 1 of 2 (50.0%)" in text
    assert text.index("AAA: 0.50% below") < text.index("BBB: 9.00% below")
    assert "CCC:" not in text
    assert "not a signal" in text


@pytest.mark.parametrize("word", ["BUY ", "SELL ", "target", "stop loss"])
def test_digest_never_uses_signal_language(demo_conn, word):
    assert word.lower() not in digest.build_digest(demo_conn).lower().replace("no signals", "")


def test_load_credentials_requires_both():
    with pytest.raises(sender.TelegramConfigError):
        sender.load_credentials({"TELEGRAM_BOT_TOKEN": "t"})
    assert sender.load_credentials({"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}) == ("t", "c")


def test_send_message_posts_plain_text():
    calls = []

    class Resp:
        status_code = 200

    sender.send_message("hi", "TOKEN", "42", post=lambda url, **kw: calls.append((url, kw)) or Resp())
    url, kw = calls[0]
    assert url.endswith("/botTOKEN/sendMessage")
    assert kw["json"] == {"chat_id": "42", "text": "hi", "disable_web_page_preview": True}
    assert "parse_mode" not in kw["json"]


def test_send_failure_never_leaks_the_token():
    def boom(url, **kw):
        raise requests.ConnectionError(url)

    with pytest.raises(sender.TelegramSendError) as err:
        sender.send_message("hi", "SECRETTOKEN", "42", post=boom)
    assert "SECRETTOKEN" not in str(err.value)

    class Bad:
        status_code = 401

    with pytest.raises(sender.TelegramSendError) as err:
        sender.send_message("hi", "SECRETTOKEN", "42", post=lambda *a, **k: Bad())
    assert "SECRETTOKEN" not in str(err.value) and "401" in str(err.value)


def test_is_session_day_uses_the_verified_calendar():
    from datetime import date
    from telegram_bot import schedule

    assert schedule.is_session_day(date(2026, 10, 1)) == (True, "calendar")
    assert schedule.is_session_day(date(2026, 10, 2)) == (False, "calendar")  # Gandhi Jayanti
    assert schedule.is_session_day(date(2026, 9, 26)) == (False, "calendar")  # Saturday


def test_is_session_day_falls_back_to_weekdays_past_the_calendar():
    from datetime import date
    from telegram_bot import schedule

    assert schedule.is_session_day(date(2027, 1, 4)) == (True, "weekday-fallback")   # Monday
    assert schedule.is_session_day(date(2027, 1, 3)) == (False, "weekday-fallback")  # Sunday


def test_pipeline_runs_steps_in_order_and_succeeds():
    from types import SimpleNamespace
    from scripts import daily_refresh

    seen = []
    ok, step, _ = daily_refresh.run_pipeline(
        run=lambda argv, **kw: seen.append(argv[1]) or SimpleNamespace(returncode=0), python="py")
    assert ok and step is None
    assert seen == ["scripts/equity_scan.py", "scripts/equity_data_acquisition.py", "scripts/equity_e4_scan.py"]


def test_pipeline_stops_at_first_failure():
    from types import SimpleNamespace
    from scripts import daily_refresh

    seen = []

    def fake(argv, **kw):
        seen.append(argv[1])
        return SimpleNamespace(returncode=1 if "acquisition" in argv[1] else 0)

    ok, step, detail = daily_refresh.run_pipeline(run=fake, python="py")
    assert (ok, step, detail) == (False, "E4 data acquisition", "exit code 1")
    assert "equity_e4_scan.py" not in " ".join(seen)
    assert "upstox_auth.py" in daily_refresh.alert_text(step, detail)


def test_pipeline_reports_a_timeout():
    import subprocess
    from scripts import daily_refresh

    def boom(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)

    ok, step, detail = daily_refresh.run_pipeline(run=boom, python="py")
    assert not ok and step == "scanner run" and "timed out" in detail


@pytest.mark.parametrize("status,persisted,expected", [
    ("COMPLETE", 10, 0), ("COMPLETE", 0, 1), ("FAILED", 10, 1), ("RUNNING", 10, 1)])
def test_acquisition_exit_code(status, persisted, expected):
    from types import SimpleNamespace
    from scripts.equity_data_acquisition import exit_code

    assert exit_code(SimpleNamespace(status=status, persisted_symbol_count=persisted)) == expected

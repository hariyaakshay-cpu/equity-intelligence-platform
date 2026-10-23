from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from equity_intel.acquisition.backfill import backfill_latest_bars
from equity_intel.acquisition.runner import run_equity_data_acquisition
import equity_intel.persistence.connection as persistence_connection
import equity_intel.persistence.db_path_guard as db_path_guard
from equity_intel.tests.test_acquisition import FakeProvider, _fixtures
from equity_intel.tests.test_equity_scan import env  # noqa: F401  (fixture reuse)

NOW = datetime(2026, 9, 30, 2, 0)


def _bar(d):
    return SimpleNamespace(timestamp=datetime.combine(d, datetime.min.time()), open=1, high=2, low=1, close=1.5, volume=10)


class Recent:
    def __init__(self, bars=(), error=None):
        self.bars, self.error, self.calls = list(bars), error, 0

    def get_historical_data(self, key, interval, start, end):
        self.calls += 1
        if self.error:
            raise self.error
        return self.bars


def test_no_refetch_when_latest_bar_is_present():
    held = [_bar(date(2026, 9, 28)), _bar(date(2026, 9, 29))]
    provider = Recent()
    result, refetched = backfill_latest_bars(provider, "k", held, date(2026, 9, 29), NOW)
    assert result == held and refetched is False and provider.calls == 0


def test_adds_only_strictly_newer_bars_and_never_rewrites_history():
    held = [_bar(date(2026, 9, 25)), _bar(date(2026, 9, 28))]
    provider = Recent([_bar(date(2026, 9, 25)), _bar(date(2026, 9, 28)), _bar(date(2026, 9, 29))])
    result, refetched = backfill_latest_bars(provider, "k", held, date(2026, 9, 29), NOW)
    assert [c.timestamp.date() for c in result] == [date(2026, 9, 25), date(2026, 9, 28), date(2026, 9, 29)]
    assert result[:2] == held and refetched is True


def test_refetch_failure_leaves_bars_unchanged_and_does_not_raise():
    held = [_bar(date(2026, 9, 28))]
    result, refetched = backfill_latest_bars(Recent(error=TimeoutError("x")), "k", held, date(2026, 9, 29), NOW)
    assert result == held and refetched is True


def test_empty_series_is_not_refetched():
    provider = Recent()
    result, refetched = backfill_latest_bars(provider, "k", [], date(2026, 9, 29), NOW)
    assert result == [] and refetched is False and provider.calls == 0


def test_before_refetch_hook_runs_only_when_a_request_is_made():
    hits = []
    backfill_latest_bars(Recent(), "k", [_bar(date(2026, 9, 29))], date(2026, 9, 29), NOW, before_refetch=lambda: hits.append(1))
    backfill_latest_bars(Recent(), "k", [_bar(date(2026, 9, 28))], date(2026, 9, 29), NOW, before_refetch=lambda: hits.append(1))
    assert hits == [1]


class DropsLatestOnLongWindows(FakeProvider):
    """Mimics Upstox: a long window omits the newest bar; a short recent window has it."""

    def __init__(self, recent_fails=False, **kw):
        super().__init__(**kw)
        self.full, self.recent_fails = {}, recent_fails

    def get_historical_data(self, key, interval, start, end):
        result = super().get_historical_data(key, interval, start, end)
        if key.startswith("NSE_INDEX"):
            return result
        if (end - start).days > 30:
            self.full[key] = result
            return result[:-1]
        if self.recent_fails:
            raise TimeoutError("recent window failed")
        return [self.full[key][-1]]


def _run(tmp_path, monkeypatch, provider):
    csv_path, master_path = _fixtures(tmp_path, ("AAA",))
    database = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    report = run_equity_data_acquisition(provider, csv_path, master_path, start_date=date(2025, 1, 1),
                                         end_date=date(2025, 12, 31), run_id="r", pacing_seconds=0, db_path=database)
    return report, database


def test_acquisition_repairs_a_dropped_latest_bar_so_the_series_reaches_the_benchmark_date(tmp_path, monkeypatch):
    provider = DropsLatestOnLongWindows()
    report, database = _run(tmp_path, monkeypatch, provider)
    assert report.successful_count == 1 and report.persisted_observation_count == 252
    with persistence_connection.connect(database) as c:
        last_stock = c.execute("SELECT MAX(trading_date) FROM acquired_observations WHERE symbol='AAA'").fetchone()[0]
        last_bench = c.execute("SELECT MAX(trading_date) FROM acquired_benchmark").fetchone()[0]
    assert last_stock == last_bench


def test_acquisition_does_not_hide_a_gap_when_the_refetch_also_fails(tmp_path, monkeypatch):
    report, _ = _run(tmp_path, monkeypatch, DropsLatestOnLongWindows(recent_fails=True))
    assert report.successful_count == 0 and report.insufficient_history_count == 1  # 251 of 252 bars stays visible


def test_scanner_v1_repairs_a_dropped_latest_bar_before_classifying(env, monkeypatch):
    from equity_intel.tests import test_equity_scan as t

    _, db_path = env
    full = [t._candle(d, close=100 + i) for i, d in enumerate(t._BENCHMARK_DATES)]

    class DropsNewestOnFirstCall(t._FakeProvider):
        def get_historical_data(self, instrument_key, interval, start_date, end_date):
            result = super().get_historical_data(instrument_key, interval, start_date, end_date)
            if instrument_key == "NSE_EQ|INE1" and self.calls.count(instrument_key) == 1:
                return result[:-1]  # first (long-window) call silently omits the newest bar
            return result

    provider = DropsNewestOnFirstCall(symbol_candles={"NSE_EQ|INE1": full, "NSE_EQ|INE2": full})
    t._install_provider(monkeypatch, provider)
    assert t.equity_scan.run_scan(now=t._NOW) == 0
    assert provider.calls.count("NSE_EQ|INE1") == 2 and provider.calls.count("NSE_EQ|INE2") == 1  # refetch only where needed

    conn = t.connection.get_read_only_connection(db_path)
    try:
        dates = {r[0] for r in conn.execute("SELECT trading_date FROM price_fetch_snapshots WHERE symbol='TCS'")}
        available = conn.execute("SELECT available_session_count FROM symbol_scan_results WHERE symbol='TCS'").fetchone()[0]
    finally:
        conn.close()
    assert dates == set(t._BENCHMARK_DATES) and available == 5


def test_bar_date_converts_aware_timestamps_to_ist_before_taking_the_date():
    from equity_intel.acquisition.backfill import _bar_date

    def bar(stamp):
        return SimpleNamespace(timestamp=stamp)

    ist = timezone(timedelta(hours=5, minutes=30))
    # Upstox's own form: IST midnight. UTC date would be the previous day.
    assert _bar_date(bar(datetime(2026, 9, 28, 0, 0, tzinfo=ist))) == date(2026, 9, 28)
    # Same instant expressed in UTC (18:30Z the day before).
    assert _bar_date(bar(datetime(2026, 9, 27, 18, 30, tzinfo=timezone.utc))) == date(2026, 9, 28)
    # Boundaries: 1 minute before UTC 18:30 is still the 27th in IST; 18:30Z exactly is the 28th.
    assert _bar_date(bar(datetime(2026, 9, 27, 18, 29, tzinfo=timezone.utc))) == date(2026, 9, 27)
    # Naive datetimes and bare dates are taken as-is (already IST wall time).
    assert _bar_date(bar(datetime(2026, 9, 28, 0, 0))) == date(2026, 9, 28)
    assert _bar_date(bar(date(2026, 9, 28))) == date(2026, 9, 28)
    assert _bar_date(bar(None)) is None


def test_backfill_does_not_re_add_a_bar_the_series_already_holds_when_stamped_in_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    held = [_bar_ist(date(2026, 9, 28))]
    # Refetch returns the same session 09-28 stamped as 09-27T18:30Z, plus 09-29: only 09-29 is new.
    recent = [SimpleNamespace(timestamp=datetime(2026, 9, 27, 18, 30, tzinfo=timezone.utc)),
              SimpleNamespace(timestamp=datetime(2026, 9, 29, 0, 0, tzinfo=ist))]
    result, _ = backfill_latest_bars(Recent(recent), "k", held, date(2026, 9, 29), NOW)
    assert [c.timestamp.astimezone(ist).date() for c in result] == [date(2026, 9, 28), date(2026, 9, 29)]


def _bar_ist(d):
    return SimpleNamespace(timestamp=datetime.combine(d, datetime.min.time(), tzinfo=timezone(timedelta(hours=5, minutes=30))))

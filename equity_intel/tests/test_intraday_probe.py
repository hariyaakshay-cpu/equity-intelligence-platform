from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from equity_intel.intraday.probe import IST, last_weekday_on_or_before, summarize_candles


def _bar(ts, volume=100, o=10, h=11, l=9, c=10):
    return SimpleNamespace(timestamp=ts, open=o, high=h, low=l, close=c, volume=volume)


def _session(day, n=75):
    start = datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST)
    return [_bar(start + timedelta(minutes=5 * i)) for i in range(n)]


def test_full_session_is_clean():
    day = datetime(2026, 10, 23)
    r = summarize_candles(_session(day), now=datetime(2026, 10, 24, 12, 0, tzinfo=IST))
    assert r["candle_count"] == 75 and r["sessions"] == 1 and r["bars_per_session"]["sessions_short_of_expected"] == 0
    assert r["duplicate_timestamps"] == 0 and r["not_on_5min_grid"] == 0 and r["outside_session"] == 0
    assert r["forming_bars"] == 0 and r["utc_offsets_seen"] == [5.5]


def test_gaps_zero_volume_duplicates_and_forming_bar_are_reported():
    day = datetime(2026, 10, 23)
    bars = _session(day, n=74)  # one bar short
    bars.append(bars[10])       # duplicate timestamp
    bars[5] = _bar(bars[5].timestamp, volume=0)
    r = summarize_candles(bars, now=bars[73].timestamp + timedelta(minutes=2))  # last real bar still forming
    assert r["duplicate_timestamps"] == 1 and r["zero_or_missing_volume"] == 1 and r["forming_bars"] >= 1
    assert r["not_monotonic"] >= 1


def test_empty_and_missing_timestamp_inputs():
    assert summarize_candles([]) == {"candle_count": 0, "missing_timestamp": 0}
    assert summarize_candles([_bar(None)])["missing_timestamp"] == 1


def test_weekday_approximation_steps_back_from_weekend():
    assert last_weekday_on_or_before(datetime(2026, 10, 24)).weekday() == 4  # Saturday -> Friday

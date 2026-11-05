"""Home-page stock scan: descriptive lists only, built from data/daily_live CSVs."""
from datetime import date, timedelta

from dashboard import stock_scan
from dashboard.app import create_app

N = 40
LAST_DATE = str(date(2026, 1, 1) + timedelta(days=N - 1))


def _write(dir_, sym, closes, vols):
    start = date(2026, 1, 1)
    lines = ["date,o,h,l,c,v"]
    for i, (c, v) in enumerate(zip(closes, vols)):
        lines.append(f"{start + timedelta(days=i)},{c},{c},{c},{c},{v}")
    (dir_ / f"{sym}.csv").write_text("\n".join(lines) + "\n")


def _universe(dir_):
    # UPPY: +10% on the last day on 4x its usual volume (~Rs 20 cr/day traded)
    _write(dir_, "UPPY", [100.0] * (N - 1) + [110.0], [2_000_000] * (N - 1) + [8_000_000])
    # DOWNY: -5% on the last day (~Rs 20 cr/day traded)
    _write(dir_, "DOWNY", [200.0] * (N - 1) + [190.0], [1_000_000] * N)
    # TINY: below the liquidity floor, never listed
    _write(dir_, "TINY", [5.0] * (N - 1) + [6.0], [1_000] * N)
    # the index file is never listed as a stock
    _write(dir_, "NIFTY500_INDEX", [1.0] * N, [0] * N)
    return dir_


def test_lists_are_descriptive_and_skip_illiquid_and_index(tmp_path):
    stock_scan._cache.clear()
    b = stock_scan.build(_universe(tmp_path))
    assert b["available"] and b["asof"] == LAST_DATE
    assert b["scanned"] == 3 and b["liquid"] == 2
    assert [m["symbol"] for m in b["gainers"]] == ["UPPY"]
    assert [m["symbol"] for m in b["losers"]] == ["DOWNY"]
    assert [m["symbol"] for m in b["volume"]] == ["UPPY"] and round(b["volume"][0]["rvol"], 1) == 4.0
    assert round(b["gainers"][0]["change_pct"], 1) == 10.0


def test_missing_dir_is_an_honest_empty_state(tmp_path):
    stock_scan._cache.clear()
    b = stock_scan.build(tmp_path / "nope")
    assert b["available"] is False and "No daily prices yet" in b["message"]


def test_home_page_shows_scan_and_momentum_sections(tmp_path):
    stock_scan._cache.clear()
    daily = tmp_path / "daily"
    daily.mkdir()
    app = create_app(db_path=tmp_path / "none.db")
    app.config["MOMENTUM_SIGNALS_DIR"] = tmp_path / "signals"
    app.config["DAILY_LIVE_DIR"] = _universe(daily)
    for url in ("/equity", "/equity/signals"):
        page = app.test_client().get(url).get_data(as_text=True)
        assert "Stock scan" in page and "UPPY" in page and "DOWNY" in page and "TINY" not in page
        assert "No momentum list yet" in page and "NOT VALIDATED" in page
        assert "Stop" not in page and "Target" not in page

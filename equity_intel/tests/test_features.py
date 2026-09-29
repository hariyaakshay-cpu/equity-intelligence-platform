from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

import equity_intel.persistence.connection as persistence_connection
import equity_intel.persistence.db_path_guard as db_path_guard
from equity_intel.features.breaks import find_last_break
from equity_intel.features.compute import compute_instrument
from equity_intel.features.config import IndicatorConfig
from equity_intel.features.runner import run_feature_scan

CFG = IndicatorConfig(ema_short=20, ema_medium=50, ema_long=200, rsi_period=14, roc_lookback=10, rvol_window=20,
                      high_window=252, atr_period=14, minimum_history_bars=252, volume_usable_bars=15,
                      volume_usable_window=20, break_low_ratio=0.5, break_high_ratio=2.0)


def _bars(closes, volume=1000.0):
    return [c + 1 for c in closes], [c - 1 for c in closes], list(closes), [volume] * len(closes)


def test_break_detector_uses_strict_thresholds_and_returns_most_recent():
    assert find_last_break([100, 50, 100], 0.5, 2.0) is None  # exactly 0.5 and 2.0 are not flagged
    brk = find_last_break([100, 49, 100, 210, 211], 0.5, 2.0)
    assert brk.index == 3 and brk.ratio == pytest.approx(2.1)
    assert find_last_break([100], 0.5, 2.0) is None


def test_clean_series_is_valid_with_all_features():
    closes = [100 + i * 0.1 for i in range(252)]
    quality, f, _ = compute_instrument("X", *_bars(closes), CFG)
    assert quality.status.value == "VALID" and quality.reason is None
    assert f.n_bars == 252 and f.w52_complete
    assert None not in (f.ema_short, f.ema_medium, f.ema_long, f.rsi, f.roc, f.relative_volume, f.atr_percent)
    assert f.prior_high_short is None and f.ema_medium_lag is None and f.relative_return is None


def test_break_truncates_history_and_long_features_become_none():
    closes = [100.0] * 100 + [30.0 + i * 0.01 for i in range(152)]
    quality, f, detail = compute_instrument("X", *_bars(closes), CFG)
    assert detail["break_date_index"] == 100
    assert quality.status.value == "INSUFFICIENT_HISTORY" and "break" in quality.reason
    assert f.n_bars == 152 and f.ema_long is None and f.ema_short is not None  # 152 < 200 bars post-break


def test_break_with_enough_post_break_bars_is_valid_but_flagged():
    closes = [100.0] * 10 + [30.0] * 260
    quality, _, detail = compute_instrument("X", *_bars(closes), CFG)
    assert quality.status.value == "VALID" and "break" in quality.reason and detail["break_ratio"] == pytest.approx(0.3)


def test_unusable_volume_yields_none_relative_volume_never_zero():
    closes = [100 + i * 0.1 for i in range(252)]
    h, l, c, _ = _bars(closes)
    volumes = [0.0] * 252
    _, f, detail = compute_instrument("X", h, l, c, volumes, CFG)
    assert f.relative_volume is None and detail["volume_usable"] is False


def _seed(database, run_status="COMPLETE"):
    with persistence_connection.connect(database) as c:
        c.execute("INSERT INTO acquisition_runs VALUES('r1','2026-01-01T00:00:00','2026-01-01T00:01:00',?,?)",
                  (run_status, json.dumps({"calendar_status": "PROVISIONAL", "constituents_sha256": "a", "instrument_master_sha256": "b"})))
        for sym in ("AAA", "SHORT"):
            c.execute("INSERT INTO instrument_mappings(run_id,symbol,exchange,mapping_status,mapping_source) VALUES('r1',?,'NSE','MAPPED','isin')", (sym,))
        c.execute("INSERT INTO symbol_acquisition_results(run_id,symbol,status,reason,observation_count) VALUES('r1','SHORT','INSUFFICIENT_HISTORY','10 observations; 252 required',10)")
        start = date(2025, 1, 1)
        for i in range(252):
            c.execute("INSERT INTO acquired_observations VALUES('r1','AAA',?,10,12,9,?,100,'Upstox','e','t','k','NSE','PROVISIONAL','a','v')",
                      ((start + timedelta(days=i)).isoformat(), 10 + i * 0.01))


def test_runner_completes_only_with_full_coverage_and_reads_stored_data(tmp_path, monkeypatch):
    database = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    _seed(database)
    summary = run_feature_scan(CFG, db_path=database)
    assert summary["status"] == "COMPLETE" and summary["universe"] == 2
    with persistence_connection.connect(database) as c:
        assert c.execute("SELECT status FROM scan_runs").fetchone()[0] == "COMPLETE"
        rows = {r["symbol"]: r["status"] for r in c.execute("SELECT symbol,status FROM data_quality_results")}
        assert rows == {"AAA": "VALID", "SHORT": "INSUFFICIENT_HISTORY"}
        assert c.execute("SELECT COUNT(*) FROM feature_sets").fetchone()[0] == 1
        assert json.loads(c.execute("SELECT indicator_config_json FROM scan_runs").fetchone()[0])["label"].startswith("provisional")


def test_runner_refuses_when_no_complete_acquisition_run(tmp_path, monkeypatch):
    database = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    _seed(database, run_status="FAILED")
    with pytest.raises(RuntimeError, match="No COMPLETE"):
        run_feature_scan(CFG, db_path=database)


def test_crash_marks_scan_failed_not_complete(tmp_path, monkeypatch):
    database = tmp_path / "db.sqlite"
    monkeypatch.setattr(db_path_guard, "CANONICAL_DB_PATH", database)
    _seed(database)
    import equity_intel.features.runner as runner
    monkeypatch.setattr(runner, "compute_instrument", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(ValueError):
        run_feature_scan(CFG, db_path=database)
    with persistence_connection.connect(database) as c:
        row = c.execute("SELECT status,failure_reason FROM scan_runs").fetchone()
        assert row["status"] == "FAILED" and "boom" in row["failure_reason"]
        assert c.execute("SELECT COUNT(*) FROM feature_sets").fetchone()[0] == 0

"""Signals page: live intraday paper board section (reads data/paper_board/<date>.json)."""
import json
from datetime import datetime

from dashboard import paper_board
from dashboard.app import create_app
from equity_intel.config import IST


def _state(date="2026-11-19", updated="10:00:00"):
    return {"date": date, "updated": updated, "mode": "PAPER - NOT VALIDATED - no orders", "notes": [], "errors": [],
            "fade": {"final": True, "alerts": [{"symbol": "KEC"}],
                     "considered": [{"symbol": "KEC", "kept": True, "reason": "ALERT"},
                                    {"symbol": "TINYCO", "kept": False, "reason": "order 1.2% of market cap (< 5%)"}]},
            "trades_today": [{"date": date, "symbol": "KEC", "amt_cr": 1200, "materiality": 0.15, "status": "OPEN",
                              "entry_open": 302.0, "live_net_pct": 1.487}],
            "surges": [{"symbol": "BEL", "ratio": 11.11, "ltp": 401.0, "change_pct": 0.25, "volume": 1, "median_volume": 1}],
            "surges_asof": "10:00:00", "scorecard": {"trades": 0}}


def _page(tmp_path, monkeypatch, now, state=None):
    (tmp_path / "2026-11-19.json").write_text(json.dumps(state or _state()))
    monkeypatch.setattr(paper_board, "datetime", type("F", (datetime,), {"now": classmethod(lambda c, tz=None: now)}))
    app = create_app(db_path=tmp_path / "none.db")
    app.config.update(PAPER_BOARD_DIR=tmp_path, MOMENTUM_SIGNALS_DIR=tmp_path, DAILY_LIVE_DIR=tmp_path)
    return app.test_client().get("/equity").get_data(as_text=True)


def test_live_board_shows_alert_surge_dropped_reason_and_refreshes(tmp_path, monkeypatch):
    page = _page(tmp_path, monkeypatch, datetime(2026, 11, 19, 10, 3, tzinfo=IST))
    assert 'id="paper-board"' in page and "PAPER ONLY" in page and "NOT VALIDATED" in page
    assert "KEC" in page and "paper short open" in page and "+1.49%" in page
    assert "BEL" in page and "11.1x" in page
    assert "TINYCO (order 1.2% of market cap (&lt; 5%))" in page
    assert 'http-equiv="refresh"' in page and "LIVE" in page


def test_old_board_is_not_live_and_hides_todays_tables(tmp_path, monkeypatch):
    page = _page(tmp_path, monkeypatch, datetime(2026, 11, 20, 10, 0, tzinfo=IST))
    assert "last run 2026-11-19" in page and 'http-equiv="refresh"' not in page
    assert "Shown during market hours." in page


def test_no_board_yet(tmp_path):
    b = paper_board.build(tmp_path / "missing")
    assert not b["available"] and "has not run yet" in b["message"]
    app = create_app(db_path=tmp_path / "none.db")
    app.config.update(PAPER_BOARD_DIR=tmp_path / "missing", MOMENTUM_SIGNALS_DIR=tmp_path, DAILY_LIVE_DIR=tmp_path)
    assert 'id="no-board"' in app.test_client().get("/equity").get_data(as_text=True)


def test_surge_test_box_shows_progress_todays_trades_and_verdict(tmp_path, monkeypatch):
    st = _state()
    st["surge_test"] = {"intact": True, "note": "ok",
                        "scorecard": {"trades": 12, "sessions": 3, "avg_net_pct": -0.21, "avg_gross_pct": -0.03,
                                      "win_rate": 0.417, "max_drawdown_pts": 2.5},
                        "review": {"verdict": "NOT_YET", "reason": "R1 needs 300 closed trades and 60 sessions"},
                        "trades_today": [{"symbol": "BEL", "status": "OPEN", "trigger_at": "2026-11-19T09:31:05",
                                          "ratio": 11.11, "entry_price": 401.0, "live_net_pct": 0.32}]}
    page = _page(tmp_path, monkeypatch, datetime(2026, 11, 19, 10, 3, tzinfo=IST), st)
    assert 'id="surge-test"' in page and "12 / 300" in page and "3 / 60 sessions" in page
    assert "Not judged yet" in page and "-0.21%" in page and "2.5 pts" in page
    assert "paper long open" in page and "09:31" in page and "+0.32%" in page
    assert 'id="surge-test-off"' not in page


def test_surge_test_box_warns_when_the_frozen_rule_changed(tmp_path, monkeypatch):
    st = _state()
    st["surge_test"] = {"intact": False, "note": "surge pre-registration changed (sha256 mismatch): surge trades not scored",
                        "scorecard": {"trades": 0, "sessions": 0}, "review": {}, "trades_today": []}
    page = _page(tmp_path, monkeypatch, datetime(2026, 11, 19, 10, 3, tzinfo=IST), st)
    assert 'id="surge-test-off"' in page and "sha256 mismatch" in page and 'id="no-surge-trades"' in page

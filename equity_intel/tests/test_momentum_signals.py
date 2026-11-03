"""12-1 momentum dashboard list: live selection, script output, page."""
import json
from datetime import date

from dashboard import momentum_signals
from dashboard.app import create_app
from equity_intel.scoring import momentum_live, momentum_12_1 as rule


def _sym(n, growth, vol=2e6, last="D0299", jump=False):
    c = [100.0 * (1 + growth) ** i for i in range(n)]
    if jump:
        c[-5] *= 2
    d = [f"D{i:04d}" for i in range(300 - n, 300)]
    assert d[-1] == last
    return d, c, c, [vol] * n


def _universe():
    s = {f"S{i:03d}": _sym(300, i / 100000) for i in range(110)}
    s["ILLIQ"] = _sym(300, 0.01, vol=10)
    s["YOUNG"] = _sym(200, 0.01)
    s["JUMP"] = _sym(300, 0.01, jump=True)
    old = _sym(300, 0.01)
    s["STALE"] = (old[0][:-1], old[1][:-1], old[2][:-1], old[3][:-1])
    return s


def test_latest_list_rule_and_skips():
    out = momentum_live.latest_list(_universe(), "D0299")
    names = [p["symbol"] for p in out["picks"]]
    assert names == [f"S{i:03d}" for i in range(109, 99, -1)]
    assert [p["rank"] for p in out["picks"]] == list(range(1, 11))
    k = 299
    c = _universe()["S109"][2]
    assert abs(out["picks"][0]["score_pct"] - 100 * (c[k - rule.SKIP] / c[k - rule.LOOKBACK] - 1)) < 1e-9
    assert out["skipped_illiquid"] == 1 and out["skipped_short_history"] == 1 and out["skipped_stale"] == 1
    assert out["corporate_action_flagged"] == ["JUMP"] and "JUMP" not in names
    assert "target" not in json.dumps(out).lower() and "stop" not in json.dumps(out).lower()


def test_too_few_eligible_gives_no_picks():
    s = {f"S{i}": _sym(300, 0.001) for i in range(50)}
    assert momentum_live.latest_list(s, "D0299")["picks"] == []


def test_page_reads_newest_file_and_flags_stale(tmp_path):
    body = momentum_live.latest_list(_universe(), "D0299")
    body.update(asof="2026-10-29", generated_at_utc="t", history_dir="x")
    (tmp_path / "momentum_12_1_2026-10-28.json").write_text(json.dumps({**body, "asof": "2026-10-28", "picks": []}))
    (tmp_path / "momentum_12_1_2026-10-29.json").write_text(json.dumps(body))
    b = momentum_signals.build(tmp_path, today=date(2026, 11, 4))
    assert b["file"].endswith("2026-10-29.json") and b["stale"] and b["age_days"] == 6
    app = create_app(db_path=tmp_path / "none.db")
    app.config["MOMENTUM_SIGNALS_DIR"] = tmp_path
    page = app.test_client().get("/equity/signals").get_data(as_text=True)
    assert "NOT VALIDATED" in page and "S109" in page and "JUMP" in page
    assert "Stop" not in page and "Target" not in page


def test_page_without_file_is_honest(tmp_path):
    app = create_app(db_path=tmp_path / "none.db")
    app.config["MOMENTUM_SIGNALS_DIR"] = tmp_path / "missing"
    page = app.test_client().get("/equity/signals")
    assert page.status_code == 200 and "No momentum list yet" in page.get_data(as_text=True)
    assert app.test_client().post("/equity/signals").status_code in (404, 405)


def test_choose_asof_skips_partly_published_session():
    lasts = ["2026-11-03"] * 287 + ["2026-11-02"] * 204
    assert momentum_live.choose_asof(lasts) == "2026-11-02"
    assert momentum_live.choose_asof(["2026-11-03"] * 96 + ["2026-11-02"] * 4) == "2026-11-03"
    assert momentum_live.choose_asof([]) is None


def test_cut_to_drops_bars_after_asof():
    s = {"A": (["d1", "d2", "d3"], [1, 2, 3], [1, 2, 3], [1, 1, 1])}
    assert momentum_live.cut_to(s, "d2")["A"] == (["d1", "d2"], [1, 2], [1, 2], [1, 1])

from equity_intel.scoring import momentum_12_1 as m


def _series(n, start=100.0, step=0.001, vol=2e6, jump_at=None):
    c = [start * (1 + step) ** i for i in range(n)]
    if jump_at is not None:
        c = [x * (0.5 if i >= jump_at else 1.0) for i, x in enumerate(c)]
    dates = [f"D{i:04d}" for i in range(n)]
    return dates, list(c), c, [vol] * n


def test_score_uses_only_past_and_skips_last_month():
    d, o, c, v = _series(300)
    rows = m.symbol_rows("A", d, o, c, v)
    k = 252
    r = rows[0]
    assert r["date"] == d[k] and abs(r["score"] - (c[k - 21] / c[0] - 1)) < 1e-12
    assert abs(r["ret"] - (c[k + 21] / o[k + 1] - 1)) < 1e-12 and r["exit_date"] == d[k + 21]
    assert len(rows) == 300 - 21 - 252


def test_break_in_formation_window_excludes():
    d, o, c, v = _series(300, jump_at=100)
    assert m.symbol_rows("A", d, o, c, v)[0]["excl"] is True


def test_top10_and_benchmark():
    rows = []
    for i in range(120):
        rows.append({"date": "X", "exit_date": "Y", "symbol": f"S{i:03d}", "score": i / 100, "traded_value": 2e8,
                     "ret": 0.05 if i >= 110 else 0.0, "excl": False})
    c = m.cohorts(rows, lambda r: True)["cohorts"][0]
    assert {s for s, _ in c["picks"]} == {f"S{i:03d}" for i in range(110, 120)}
    assert abs(c["excess"] - (0.05 - m.COST - 0.5 / 120)) < 1e-12


def test_too_few_eligible_dates_dropped():
    rows = [{"date": "X", "exit_date": "Y", "symbol": f"S{i}", "score": 0.1, "traded_value": 2e8, "ret": 0.0, "excl": False}
            for i in range(50)]
    assert m.cohorts(rows, lambda r: True)["cohorts"] == []

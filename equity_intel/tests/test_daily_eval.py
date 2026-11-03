from equity_intel.scoring import daily_eval as de


def _row(d, s, short, medium, tv=2e8, r5=0.01, r20=0.02, x5=0, x20=0):
    return {"date": d, "symbol": s, "short": str(short), "medium": str(medium), "traded_value": str(tv),
            "ret5": str(r5), "excl5": str(x5), "ret20": str(r20), "excl20": str(x20)}


def test_top10_cutoff_liquidity_and_excess():
    rows = [_row("2024-01-01", f"S{i:02d}", 70 + i, 0, r5=0.05) for i in range(12)]
    rows += [_row("2024-01-01", "LOW", 99, 0, r5=0.10, tv=5e7)]          # illiquid: not eligible anywhere
    rows += [_row("2024-01-01", "B", 10, 0, r5=-0.01)]                  # below cutoff, only in benchmark
    c = de.cohorts(rows, "short")["cohorts"][0]
    assert c["n"] == 10 and {s for s, _ in c["picks"]} == {f"S{i:02d}" for i in range(2, 12)}
    bench = (12 * 0.05 - 0.01) / 13
    assert abs(c["excess"] - (0.05 - de.COST - bench)) < 1e-12


def test_exclusion_drops_pick_without_refill_and_from_bench():
    rows = [_row("2024-01-01", "A", 90, 0, r5=0.5, x5=1), _row("2024-01-01", "B", 80, 0, r5=0.02),
            _row("2024-01-01", "C", 10, 0, r5=0.0)]
    res = de.cohorts(rows, "short")
    c = res["cohorts"][0]
    assert [s for s, _ in c["picks"]] == ["B"] and res["excluded_picks"] == 1
    assert abs(c["bench"] - 0.01) < 1e-12


def test_missing_forward_return_not_traded():
    rows = [_row("2024-01-01", "A", 90, 90, r20="")]
    assert de.cohorts(rows, "medium")["cohorts"] == []


def test_tie_break_by_symbol():
    rows = [_row("2024-01-01", s, 80, 0) for s in ["Z", "A", "M"]] + [_row("2024-01-01", f"X{i}", 80, 0) for i in range(10)]
    picks = [s for s, _ in de.cohorts(rows, "short")["cohorts"][0]["picks"]]
    assert picks[0] == "A" and "Z" not in picks


def test_bootstrap_deterministic_and_centered():
    x = [0.01] * 50 + [-0.01] * 50
    a, b = de.block_bootstrap_means(x, 5, n=500), de.block_bootstrap_means(x, 5, n=500)
    assert a == b and a[0] <= 0 <= a[-1]


def test_summary_fail_when_negative():
    rows = [_row(f"2024-01-{d:02d}", "A", 90, 0, r5=-0.02) for d in range(1, 29)]
    rows += [_row(f"2024-01-{d:02d}", "B", 10, 0, r5=0.0) for d in range(1, 29)]
    s = de.summarize(de.cohorts(rows, "short"), "short")
    assert s["verdict"] == "FAIL" and not s["dev_qualifies_for_holdout"]

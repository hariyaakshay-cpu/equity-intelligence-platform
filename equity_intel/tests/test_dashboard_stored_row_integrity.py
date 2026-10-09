"""dashboard.stored_row_integrity.check_rows: MATCH / MISMATCH / UNAVAILABLE for one symbol's stored rows."""
from dashboard import stock_detail, stored_row_integrity
from equity_intel.scanner.snapshots import compute_content_hash


def _row(trading_date, close="100.00", volume=1000, tamper=False):
    prices = ["99.00", "102.00", "98.00", close]
    stored_hash = compute_content_hash(trading_date, *prices, volume)
    if tamper:
        stored_hash = "0" * 64
    return {"trading_date": trading_date, "open": prices[0], "high": prices[1], "low": prices[2],
            "close": prices[3], "volume": volume, "content_hash": stored_hash}


def test_label_is_the_stored_row_integrity_wording():
    assert stored_row_integrity.LABEL == "stored-row integrity" == stock_detail.HASH_CHECK_LABEL


def test_match_when_every_stored_row_reproduces_its_hash():
    out = stored_row_integrity.check_rows([_row("2026-09-23"), _row("2026-09-24", close="101.50")])
    assert out == {"label": "stored-row integrity", "state": "MATCH", "bars": 2, "mismatched": []}


def test_mismatch_lists_the_dates_whose_stored_hash_differs():
    rows = [_row("2026-09-23"), _row("2026-09-24", tamper=True), _row("2026-09-25", tamper=True)]
    out = stored_row_integrity.check_rows(rows)
    assert out["state"] == "MISMATCH" and out["bars"] == 3 and out["mismatched"] == ["2026-09-24", "2026-09-25"]


def test_a_stored_value_edited_after_hashing_is_a_mismatch():
    row = _row("2026-09-23")
    row["close"] = "100.01"  # the stored text no longer matches the hash that was written
    assert stored_row_integrity.check_rows([row])["state"] == "MISMATCH"


def test_no_rows_is_unavailable_never_match():
    out = stored_row_integrity.check_rows([])
    assert out == {"label": "stored-row integrity", "state": "UNAVAILABLE", "bars": 0, "mismatched": []}


def test_a_custom_recompute_function_is_used_for_every_row():
    seen = []

    def recompute(row):
        seen.append(row["trading_date"])
        return "x"

    out = stored_row_integrity.check_rows([_row("2026-09-23"), _row("2026-09-24")], recompute)
    assert seen == ["2026-09-23", "2026-09-24"] and out["state"] == "MISMATCH"


def test_default_recompute_is_looked_up_in_this_module_so_it_can_be_spied_on(monkeypatch):
    calls = []
    monkeypatch.setattr(stored_row_integrity, "compute_content_hash_from_stored_row",
                        lambda row: calls.append(row["trading_date"]) or row["content_hash"])
    stored_row_integrity.check_rows([_row("2026-09-23"), _row("2026-09-24")])
    assert calls == ["2026-09-23", "2026-09-24"]

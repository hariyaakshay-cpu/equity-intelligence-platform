import pytest

from equity_intel.alerts import telegram_v0


def _body(n=3, outdated=False):
    cands = [dict(rank=i + 1, symbol=f"S{i}", composite=90 - i, trend=20, momentum=18, relative_strength=16,
                  volume=20, structure=12, close=100.0 + i, watchlist=True) for i in range(n)]
    return {"available": True, "meta": {"asof_date": "2026-10-23", "candidate_cutoff": 70, "watchlist_limit": 10},
            "counts": {"candidates": n}, "candidates": cands, "outdated": outdated, "expected_latest_session": "2026-10-23"}


def test_message_is_labelled_and_lists_watchlist_rows():
    text = telegram_v0.format_message(_body())
    assert "PROVISIONAL" in text and "not trade advice" in text and "1. S0 score 90" in text
    assert "Intraday signals are not built" in text


def test_message_warns_when_outdated_and_when_empty_and_when_unavailable():
    assert "WARNING: outdated" in telegram_v0.format_message(_body(outdated=True))
    assert "No stock reaches" in telegram_v0.format_message(_body(n=0))
    assert "PROVISIONAL" in telegram_v0.format_message({"available": False, "message": "none"})


def test_message_never_exceeds_telegram_limit():
    assert len(telegram_v0.format_message(_body(n=500))) <= telegram_v0.TELEGRAM_LIMIT


def test_send_refuses_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        telegram_v0.send("x")


def test_message_has_short_and_medium_blocks():
    body = _body()
    body["horizons"] = {"short": [dict(rank=1, symbol="SHT", score=90, watchlist=True)],
                        "medium": [dict(rank=1, symbol="MED", score=85, watchlist=True)]}
    text = telegram_v0.format_message(body)
    assert "SHORT TERM" in text and "1. SHT 90%" in text and "MEDIUM TERM" in text and "1. MED 85%" in text
    empty = telegram_v0.format_message(_body())
    assert empty.count("none above the cutoff") == 2

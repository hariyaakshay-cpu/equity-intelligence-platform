from datetime import date

from equity_intel.paper_board import notify as nt

STATE = {"date": date(2026, 11, 20), "updated": "08:41:05", "data_asof": date(2026, 11, 19),
         "prices_stale": False, "liquid_watched": 450, "errors": [], "trades_today": [],
         "scorecard": {"trades": 0}}
ALERT = {"symbol": "KEC", "amt_cr": 1200.0, "materiality": 0.152, "prev_close": 310.95}
SURGE = {"symbol": "TATATECH", "ratio": 18.59, "ltp": 703.1, "change_pct": 7.07,
         "volume": 7406743, "median_volume": 506431}


def test_every_message_carries_the_paper_banner():
    msgs = [nt.start_message(STATE, True), nt.fade_message([ALERT], date(2026, 11, 20), True),
            nt.fade_message([ALERT], date(2026, 11, 20), False), nt.surge_message([SURGE], "11:05:00"),
            nt.warning_message(["09:31:05 quotes: HTTPError: 401"]), nt.holiday_message(date(2026, 11, 20)),
            nt.summary_message(STATE, nt.empty_sent())]
    assert all(m.startswith(nt.BANNER) for m in msgs)


def test_start_message_flags_stale_prices_and_missing_token():
    text = nt.start_message({**STATE, "prices_stale": True}, quotes_on=False)
    assert "STALE" in text and "OFF (no Upstox token)" in text
    assert "STALE" not in nt.start_message(STATE, True)


def test_fade_message_none_without_alerts_and_final_vs_heads_up():
    assert nt.fade_message([], date(2026, 11, 20), True) is None
    final = nt.fade_message([ALERT], date(2026, 11, 20), True)
    assert "FADE ALERT 2026-11-20" in final and "KEC: order Rs 1,200 cr = 15.2% of market cap" in final
    early = nt.fade_message([ALERT], date(2026, 11, 20), False)
    assert "heads-up for 2026-11-20" in early and "final list comes at 09:00" in early


def test_each_surge_stock_is_sent_once_a_day():
    sent = nt.empty_sent()
    assert nt.new_surges([SURGE], sent) == [SURGE]
    sent["surges"].append("TATATECH")
    assert nt.new_surges([SURGE], sent) == []
    assert nt.surge_message([], "11:05:00") is None
    text = nt.surge_message([SURGE], "11:05:00")
    assert "TATATECH: 18.6x its usual volume so far, +7.07% on the day, last 703.10" in text
    assert "not a buy/sell call" in text


def test_a_repeating_error_is_sent_once():
    sent = nt.empty_sent()
    errs = ["09:31:05 quotes: HTTPError: 401 Unauthorized", "09:36:05 quotes: HTTPError: 401 Unauthorized",
            "09:01:00 announcements: ConnectionError: reset"]
    first = nt.new_errors(errs, sent)
    assert first == [errs[0], errs[2]]
    sent["errors"] = nt.error_keys(first)
    assert nt.new_errors(errs, sent) == []


def test_summary_reports_fade_result_surges_and_scorecard():
    closed = {"symbol": "KEC", "status": "CLOSED", "net_pct": "0.8"}
    void = {"symbol": "ABC", "status": "VOID", "reason": "market closed today"}
    st = {**STATE, "trades_today": [closed, void],
          "scorecard": {"trades": 3, "win_rate": 0.667, "avg_net_pct": 0.21}}
    text = nt.summary_message(st, {**nt.empty_sent(), "surges": ["A", "B"]})
    assert "Fade KEC: net +0.80%" in text and "Fade ABC: VOID market closed today" in text
    assert "flagged today: 2 stocks" in text and "3 trades, win rate 67%, average net +0.21%" in text
    assert "No fade trade today" in nt.summary_message(STATE, nt.empty_sent())


def test_long_messages_are_clipped_to_the_telegram_limit():
    rows = [{**SURGE, "symbol": f"S{i:04d}"} for i in range(400)]
    assert len(nt.surge_message(rows, "11:05:00")) <= nt.LIMIT

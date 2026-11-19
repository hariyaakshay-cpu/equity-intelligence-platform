"""Telegram messages for the live intraday PAPER board - pure text, no I/O, no orders.

The board (scripts/equity_paper_board.py) decides when to send and sends with
equity_intel.alerts.telegram_v0.send(). This module only builds the text and
keeps a per-day record of what was already sent (a plain dict the board saves
as data/paper_board/<date>.sent.json), so a restart never repeats a message.
Every message starts with BANNER. Signals only: the owner places any order himself.
"""
from __future__ import annotations

BANNER = "PAPER - NOT VALIDATED - signals only, no orders placed"
LIMIT = 4096                      # Telegram message limit (characters)


def empty_sent() -> dict:
    return {"start": False, "fade": False, "holiday": False, "summary": False, "evening": False,
            "surges": [], "errors": []}


def _clip(lines: list[str]) -> str:
    text = "\n".join(lines)
    return text if len(text) <= LIMIT else text[: LIMIT - 20] + "\n...(truncated)"


def start_message(state: dict, quotes_on: bool) -> str:
    """First cycle of the day: the board is alive, with its data date and quote status."""
    stale = " - STALE, previous session missing" if state.get("prices_stale") else ""
    quotes = "ON" if quotes_on else "OFF (no Upstox token)"
    return _clip([BANNER,
                  f"Board started {state['updated']} IST for {state['date']}.",
                  f"Daily prices as of {state['data_asof']}{stale}.",
                  f"Watching {state['liquid_watched']} liquid stocks; live quotes {quotes}."])


def fade_message(alerts: list[dict], session, final: bool) -> str | None:
    """Order-win fade alerts for `session`; final=False is the evening heads-up. None if no alert."""
    if not alerts:
        return None
    head = (f"FADE ALERT {session}: short at the 09:15 open, cover by the close." if final else
            f"Fade heads-up for {session}: short at the open, cover by the close. "
            "Provisional - the final list comes at 09:00.")
    lines = [BANNER, head]
    for a in alerts:
        lines.append(f"- {a['symbol']}: order Rs {a['amt_cr']:,.0f} cr = {a['materiality']:.1%} of market cap, "
                     f"previous close {a['prev_close']:.2f}")
    lines.append("This rule failed its backtest (one stock made 55% of the profit).")
    return _clip(lines)


def new_surges(surges: list[dict], sent: dict) -> list[dict]:
    """Surge rows whose stock has not been sent today (each stock once a day)."""
    seen = set(sent.get("surges", []))
    return [s for s in surges if s["symbol"] not in seen]


def surge_message(rows: list[dict], asof: str) -> str | None:
    if not rows:
        return None
    lines = [BANNER, f"New volume surges {asof} IST - a watchlist, not a buy/sell call:"]
    for s in rows:
        move = "" if s.get("change_pct") is None else f", {s['change_pct']:+.2f}% on the day"
        ltp = "" if s.get("ltp") is None else f", last {s['ltp']:.2f}"
        lines.append(f"- {s['symbol']}: {s['ratio']:.1f}x its usual volume so far{move}{ltp}")
    return _clip(lines)


def _error_key(error: str) -> str:
    """'09:31:05 quotes: HTTPError: 401 ...' -> 'quotes: HTTPError' (time and detail dropped)."""
    rest = error.split(" ", 1)[1] if " " in error else error
    return ":".join(rest.split(":")[:2]).strip()


def error_keys(errors: list[str]) -> list[str]:
    return [_error_key(e) for e in errors]


def new_errors(errors: list[str], sent: dict) -> list[str]:
    """One warning per distinct kind of error a day, so a repeating failure is sent once."""
    seen, out = set(sent.get("errors", [])), []
    for e in errors:
        k = _error_key(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def warning_message(errors: list[str]) -> str | None:
    if not errors:
        return None
    return _clip([BANNER, "Board warning (it keeps running; details in the log):"] + [f"- {e}" for e in errors])


def holiday_message(today) -> str:
    return _clip([BANNER, f"No stock has traded by 09:30 on {today}: market closed (holiday?). "
                          "Board stopped; today's fade alerts are void."])


def summary_message(state: dict, sent: dict) -> str:
    """15:31: the day's fade paper result, surge count and the running fade scorecard."""
    lines = [BANNER, f"Day summary {state['date']}"]
    trades = state.get("trades_today") or []
    for t in trades:
        net = t.get("net_pct")
        if net not in (None, ""):
            lines.append(f"- Fade {t['symbol']}: net {float(net):+.2f}% after costs at the 15:31 price "
                         "(re-marked with the official close tomorrow)")
        else:
            lines.append(f"- Fade {t['symbol']}: {t.get('status', '')} {t.get('reason', '')}".rstrip())
    if not trades:
        lines.append("- No fade trade today.")
    lines.append(f"- Volume surges flagged today: {len(sent.get('surges', []))} stocks.")
    sc = state.get("scorecard") or {}
    if sc.get("trades"):
        lines.append(f"- Fade scorecard: {sc['trades']} trades, win rate {sc['win_rate']:.0%}, "
                     f"average net {sc['avg_net_pct']:+.2f}%.")
    else:
        lines.append("- Fade scorecard: no closed trades yet.")
    if state.get("errors"):
        lines.append(f"- {len(state['errors'])} warning(s) today, see the log.")
    return _clip(lines)

"""Live intraday paper board - pure functions, no I/O, no orders.

PAPER ONLY, NOT VALIDATED. Two panels:
  1. Order-win fade alerts: the frozen order-win rules (order wins >= 5% of
     market cap, liquid, EQ series, entry-session rule, 20-session non-overlap)
     applied to today's NSE announcements. Paper short at the official open,
     cover at the close, 0.50% round trip. The rule FAILED its test
     (research/announcements/order_wins/fade/fade_result.md); this tracks it live.
  2. Volume surges: volume so far vs the 20-session median daily volume, scaled
     by the share of the session elapsed. A watchlist, not a buy/sell call.
"""
from __future__ import annotations

from datetime import date, datetime, time
from statistics import median

import pandas as pd

from equity_intel.announcements import event_study as es
from equity_intel.announcements import order_wins as ow

FADE_MATERIALITY = 0.05
COST = 0.005
SURGE_MIN_RATIO = 1.5
SURGE_MIN_VALUE_CR = 10.0       # 20-session median close x volume, same bar as the daily scan
SURGE_FIRST_MINUTES = 15        # no surge ratio before 09:30 (too noisy)
SURGE_TOP = 15
MARKET_OPEN, MARKET_CLOSE = time(9, 15), time(15, 30)
SESSION_MINUTES = 375


def fade_candidates(ann: pd.DataFrame, today: date, sessions: list[date], daily: dict,
                    shares: dict, recent: dict) -> tuple[list[dict], list[dict]]:
    """Order wins whose entry session is `today`.

    ann: es.load_announcements() frame; sessions: trading days ending with today;
    daily: symbol -> DataFrame(o,h,l,c,v) indexed by date (history before today);
    shares: symbol -> (issued_size, series); recent: symbol -> last fade entry date
    on this board (20-session non-overlap). Returns (alerts, considered) where
    considered lists every order win for today with the reason it was or was not kept.
    """
    if sessions[-1] != today:
        raise ValueError("sessions must end with today")
    pos = {s: i for i, s in enumerate(sessions)}
    i = pos[today]
    prior = sessions[max(0, i - ow.LIQ_WINDOW):i]
    wins = ow.extract_order_wins(ann) if len(ann) else ann
    best: dict = {}
    for r in wins.itertuples(index=False):
        if es.entry_session(r.event_ts, sessions) != today:
            continue
        if r.symbol not in best or r.amt_cr > best[r.symbol]["amt_cr"]:
            best[r.symbol] = {"symbol": r.symbol, "amt_cr": float(r.amt_cr),
                              "event_ts": str(r.event_ts), "text": str(r.text)[:300]}
    alerts, considered = [], []
    for sym in sorted(best):
        c = dict(best[sym])
        reason = None
        px = daily.get(sym)
        issued, series = shares.get(sym, (None, None))
        last = recent.get(sym)
        if last is not None and last in pos and i - pos[last] <= ow.NON_OVERLAP:
            reason = "fade on this stock within 20 sessions"
        elif px is None:
            reason = "no daily prices"
        elif not issued:
            reason = "no share count (not in MCAP file)"
        elif series != "EQ":
            reason = f"series {series}, not EQ (no intraday short)"
        elif sessions[i - 1] not in px.index:
            reason = "no close for the previous session"
        else:
            val = ow._median_value(px, prior)
            mcap_cr = issued * px.loc[sessions[i - 1], "c"] / 1e7
            c.update(mcap_cr=round(mcap_cr, 2), materiality=round(c["amt_cr"] / mcap_cr, 4),
                     prev_close=float(px.loc[sessions[i - 1], "c"]))
            if val is None or val < ow.EVENT_LIQ_MIN:
                reason = "illiquid (median value < Rs 2 cr)"
            elif c["materiality"] < FADE_MATERIALITY:
                reason = f"order {c['materiality']:.1%} of market cap (< 5%)"
        c["kept"] = reason is None
        c["reason"] = reason or "ALERT: paper short at open"
        considered.append(c)
        if reason is None:
            alerts.append(c)
    return alerts, considered


def short_result(o: float, h: float, l: float, c: float) -> dict:
    """Paper short opened at the open and covered at the close, after costs."""
    if o <= 0 or c <= 0:
        return {"status": "VOID", "reason": "missing price"}
    if o == l == c:
        return {"status": "VOID", "reason": "locked at the low, short not fillable"}
    if o == h == c:
        return {"status": "VOID", "reason": "locked at the high at entry"}
    gross = (o - c) / o
    return {"status": "CLOSED", "gross_pct": round(gross * 100, 3),
            "net_pct": round((gross - COST) * 100, 3)}


def baselines(daily: dict, today: date, sessions: list[date]) -> dict:
    """symbol -> (median daily volume, median daily value in Rs cr) over the 20 sessions before today."""
    i = sessions.index(today)
    prior = sessions[max(0, i - ow.LIQ_WINDOW):i]
    out = {}
    for sym, px in daily.items():
        rows = px.reindex(prior).dropna(subset=["c", "v"])
        if len(rows) < ow.LIQ_MIN_ROWS:
            continue
        out[sym] = (float(median(rows["v"])), float(median(rows["c"] * rows["v"])) / 1e7)
    return out


def elapsed_fraction(now: datetime) -> float:
    start = datetime.combine(now.date(), MARKET_OPEN)
    minutes = (now - start).total_seconds() / 60
    return max(0.0, min(1.0, minutes / SESSION_MINUTES))


def surges(quotes: dict, base: dict, now: datetime) -> list[dict]:
    """quotes: symbol -> {"ltp", "volume", "prev_close"}. Liquid stocks only; top by ratio."""
    frac = elapsed_fraction(now)
    if frac * SESSION_MINUTES < SURGE_FIRST_MINUTES:
        return []
    rows = []
    for sym, q in quotes.items():
        b = base.get(sym)
        if not b or b[0] <= 0 or b[1] < SURGE_MIN_VALUE_CR or not q.get("volume"):
            continue
        ratio = q["volume"] / (b[0] * frac)
        if ratio < SURGE_MIN_RATIO:
            continue
        pc = q.get("prev_close") or 0
        rows.append({"symbol": sym, "ratio": round(ratio, 2), "ltp": q.get("ltp"),
                     "change_pct": round((q["ltp"] / pc - 1) * 100, 2) if pc and q.get("ltp") else None,
                     "volume": int(q["volume"]), "median_volume": int(b[0])})
    rows.sort(key=lambda r: (-r["ratio"], r["symbol"]))
    return rows[:SURGE_TOP]


def scorecard(trades: list[dict]) -> dict:
    """Over CLOSED paper trades only."""
    done = [t for t in trades if t.get("status") == "CLOSED" and t.get("net_pct") is not None]
    if not done:
        return {"trades": 0}
    nets = [float(t["net_pct"]) for t in done]
    return {"trades": len(nets), "wins": sum(n > 0 for n in nets),
            "win_rate": round(sum(n > 0 for n in nets) / len(nets), 3),
            "avg_net_pct": round(sum(nets) / len(nets), 3), "total_net_pct": round(sum(nets), 3),
            "best_pct": max(nets), "worst_pct": min(nets),
            "first": min(t["date"] for t in done), "last": max(t["date"] for t in done)}


def parse_upstox_quotes(payload: dict, key_to_symbol: dict) -> dict:
    """Upstox v2 GET /market-quote/quotes reply -> symbol -> {ltp, volume, open, high, low, prev_close}.

    Entries are mapped back by their `instrument_token` (e.g. NSE_EQ|INE...), not by
    the reply's own key. prev_close = last_price - net_change. Unknown or malformed
    entries are skipped.
    """
    out = {}
    for entry in (payload or {}).get("data", {}).values():
        try:
            sym = key_to_symbol.get(entry.get("instrument_token"))
            if sym is None:
                continue
            ohlc = entry.get("ohlc") or {}
            ltp = float(entry["last_price"])
            net = entry.get("net_change")
            out[sym] = {"ltp": ltp, "volume": int(entry.get("volume") or 0),
                        "open": float(ohlc.get("open") or 0), "high": float(ohlc.get("high") or 0),
                        "low": float(ohlc.get("low") or 0),
                        "prev_close": round(ltp - float(net), 4) if net is not None else None}
        except (KeyError, TypeError, ValueError):
            continue
    return out

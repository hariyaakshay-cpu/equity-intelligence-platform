"""Round-3 intraday setups (docs/architecture/equity_intel_intraday_setups_v2_preregistration_DRAFT.md).

Pure functions over closed 5-minute bars. No I/O, no broker path. Parameters are frozen by the
pre-registration and must not be changed after results. Market context is computed from the
universe itself: at each bar index, BREADTH = share of stocks closing above their previous
session close, MEDIAN_RET = median of close / previous close - 1. A rule sees only bars up to the trigger bar.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import time
from typing import Dict, List, Optional, Sequence, Tuple

from equity_intel.intraday.backtest import MAX_SIGNALS_PER_DAY, trade_for
from equity_intel.intraday.setups import Bar, _clean_prefix, orb_long

ROUND3_SETUPS = ["R3_BREADTH_ORB_LONG", "R3_RS_LEADER_LONG", "R3_VOLUME_SURGE_LONG"]
MIN_STOCKS = 50
BREADTH_MIN, MEDIAN_MIN = 0.60, 0.0025
RS_START, RS_END = time(10, 15), time(12, 0)
RS_MARGIN, RS_NEAR_HIGH = 0.01, 0.998
VOL_START, VOL_END = time(9, 30), time(13, 0)
VOL_MULT, VOL_WINDOW, VOL_MAX_IDX = 3.0, 20, 45  # idx 45 = bar closing 13:00

Context = List[Optional[Tuple[float, float]]]  # per bar index: (breadth, median_ret)


def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def market_context(sessions: Dict[str, Dict[str, Sequence[Bar]]], min_stocks: int = MIN_STOCKS) -> Dict[str, Context]:
    acc: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    for days in sessions.values():
        dates = sorted(days)
        for k in range(1, len(dates)):
            prev_close = days[dates[k - 1]][-1].c
            if prev_close <= 0:
                continue
            for i, b in enumerate(days[dates[k]]):
                acc[dates[k]][i].append(b.c / prev_close - 1.0)
    ctx: Dict[str, Context] = {}
    for d, per in acc.items():
        row: Context = []
        for i in range(max(per) + 1):
            xs = per.get(i, [])
            row.append(None if len(xs) < min_stocks else (sum(1 for x in xs if x > 0) / len(xs), _median(xs)))
        ctx[d] = row
    return ctx


def volume_baseline(days: Dict[str, Sequence[Bar]], dates: Sequence[str], k: int) -> Optional[List[float]]:
    """Median volume per bar index over the previous VOL_WINDOW available sessions of this symbol."""
    if k < VOL_WINDOW:
        return None
    prev = [days[d] for d in dates[k - VOL_WINDOW:k]]
    n = min(VOL_MAX_IDX + 1, min(len(b) for b in prev))
    return [_median([b[i].v for b in prev]) for i in range(n)]


def breadth_orb_long(bars: Sequence[Bar], day_ctx: Context) -> Optional[int]:
    trig = orb_long(bars)
    if trig is None or trig >= len(day_ctx) or day_ctx[trig] is None:
        return None
    breadth, med = day_ctx[trig]
    return trig if breadth >= BREADTH_MIN and med >= MEDIAN_MIN else None


def rs_leader_long(bars: Sequence[Bar], prev_close: float, day_ctx: Context) -> Optional[int]:
    hi = 0.0
    for i, b in enumerate(bars):
        if not _clean_prefix(bars, i) or not b.v:
            return None
        hi = max(hi, b.h)
        if b.close_time > RS_END:
            return None
        if b.close_time < RS_START or i >= len(day_ctx) or day_ctx[i] is None:
            continue
        med = day_ctx[i][1]
        if med >= 0 and b.c / prev_close - 1.0 >= med + RS_MARGIN and b.c >= RS_NEAR_HIGH * hi:
            return i
    return None


def volume_surge_long(bars: Sequence[Bar], base: Optional[Sequence[float]]) -> Optional[int]:
    if base is None:
        return None
    cum_pv = cum_v = 0.0
    prior_high = 0.0
    for i, b in enumerate(bars):
        if not _clean_prefix(bars, i) or not b.v:
            return None
        cum_pv += (b.h + b.l + b.c) / 3.0 * b.v
        cum_v += b.v
        if b.close_time > VOL_END or i >= len(base):
            return None
        if (b.close_time >= VOL_START and i >= 1 and base[i] > 0 and b.v >= VOL_MULT * base[i]
                and b.c > prior_high and b.c > cum_pv / cum_v):
            return i
        prior_high = max(prior_high, b.h)
    return None


def run_round3(setup: str, sessions: Dict[str, Dict[str, Sequence[Bar]]], ctx: Dict[str, Context],
               date_filter=None) -> List[dict]:
    per_day: Dict[str, list] = defaultdict(list)
    for sym, days in sessions.items():
        dates = sorted(days)
        for k, d in enumerate(dates):
            if k == 0 or (date_filter is not None and d not in date_filter) or d not in ctx:
                continue
            bars, day_ctx = days[d], ctx[d]
            prev_close = days[dates[k - 1]][-1].c
            if setup == "R3_BREADTH_ORB_LONG":
                trig = breadth_orb_long(bars, day_ctx)
            elif setup == "R3_RS_LEADER_LONG":
                trig = rs_leader_long(bars, prev_close, day_ctx) if prev_close > 0 else None
            elif setup == "R3_VOLUME_SURGE_LONG":
                trig = volume_surge_long(bars, volume_baseline(days, dates, k))
            else:
                raise ValueError(f"unknown setup {setup!r}")
            if trig is None:
                continue
            t = trade_for(bars, trig)
            if t:
                t.update(symbol=sym, date=d)
                per_day[d].append(t)
    trades: List[dict] = []
    for d in sorted(per_day):
        ranked = sorted(per_day[d], key=lambda t: (t["trigger_ts"], t["symbol"]))  # tie-break: first trigger time, then symbol
        trades.extend(ranked[:MAX_SIGNALS_PER_DAY])
    return trades

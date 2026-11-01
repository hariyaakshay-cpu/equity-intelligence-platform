"""Round-4 intraday setups (docs/architecture/equity_intel_intraday_setups_v3_preregistration_DRAFT.md).

Pure functions over closed 5-minute bars, no I/O. Parameters are frozen by the pre-registration.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import time
from statistics import median
from typing import Dict, List, Optional, Sequence

from equity_intel.intraday.backtest import MAX_SIGNALS_PER_DAY, trade_for
from equity_intel.intraday.setups import Bar, _clean_prefix, orb_long

ROUND4_SETUPS = ["R4_HIGHVOL_ORB_LONG", "R4_GAP_VOLUME_LONG"]
WINDOW = 20
TOP_FRACTION = 0.20
OR_BARS, OR_MIN_WIDTH = 3, 0.006
GAP_MIN, FIRST3_VOL_MULT = 0.02, 2.0
GAP_START, GAP_END = time(9, 30), time(11, 0)


def aux_stats(sessions: Dict[str, Dict[str, Sequence[Bar]]]):
    """vol20[date][symbol] = mean daily range over the symbol's previous 20 sessions; thr[date] = top-20% cut-off;
    first3[symbol][date] = volume of the first 3 bars."""
    first3: Dict[str, Dict[str, float]] = {}
    vol20: Dict[str, Dict[str, float]] = defaultdict(dict)
    for sym, days in sessions.items():
        dates = sorted(days)
        rng = {d: (max(b.h for b in days[d]) - min(b.l for b in days[d])) / days[d][-1].c for d in dates if days[d][-1].c > 0}
        first3[sym] = {d: sum(b.v for b in days[d][:OR_BARS]) for d in dates}
        for k in range(WINDOW, len(dates)):
            prev = [rng[d] for d in dates[k - WINDOW:k] if d in rng]
            if len(prev) == WINDOW:
                vol20[dates[k]][sym] = sum(prev) / WINDOW
    thr = {}
    for d, per in vol20.items():
        vals = sorted(per.values())
        thr[d] = vals[int((1.0 - TOP_FRACTION) * len(vals))]
    return vol20, thr, first3


def highvol_orb_long(bars: Sequence[Bar], is_top: bool) -> Optional[int]:
    if not is_top or len(bars) <= OR_BARS:
        return None
    or_low = min(b.l for b in bars[:OR_BARS])
    or_high = max(b.h for b in bars[:OR_BARS])
    if or_low <= 0 or (or_high - or_low) / or_low < OR_MIN_WIDTH:
        return None
    return orb_long(bars)


def gap_volume_long(bars: Sequence[Bar], prev_close: float, base_first3: Optional[float]) -> Optional[int]:
    if base_first3 is None or base_first3 <= 0 or prev_close <= 0 or len(bars) <= OR_BARS:
        return None
    if not _clean_prefix(bars, OR_BARS - 1) or any(not b.v for b in bars[:OR_BARS]):
        return None
    if bars[0].o < (1.0 + GAP_MIN) * prev_close or sum(b.v for b in bars[:OR_BARS]) < FIRST3_VOL_MULT * base_first3:
        return None
    first_high = max(b.h for b in bars[:OR_BARS])
    for i in range(OR_BARS, len(bars)):
        b = bars[i]
        if not _clean_prefix(bars, i) or b.close_time > GAP_END:
            return None
        if b.close_time >= GAP_START and b.v and b.c > first_high:
            return i
    return None


def run_round4(setup: str, sessions: Dict[str, Dict[str, Sequence[Bar]]], aux, date_filter=None) -> List[dict]:
    vol20, thr, first3 = aux
    per_day: Dict[str, list] = defaultdict(list)
    for sym, days in sessions.items():
        dates = sorted(days)
        for k, d in enumerate(dates):
            if k < WINDOW or (date_filter is not None and d not in date_filter):
                continue
            bars = days[d]
            if setup == "R4_HIGHVOL_ORB_LONG":
                v = vol20.get(d, {}).get(sym)
                trig = highvol_orb_long(bars, v is not None and d in thr and v >= thr[d])
            elif setup == "R4_GAP_VOLUME_LONG":
                prev_close = days[dates[k - 1]][-1].c
                base = median(first3[sym][x] for x in dates[k - WINDOW:k])
                trig = gap_volume_long(bars, prev_close, base)
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
        trades.extend(sorted(per_day[d], key=lambda t: (t["trigger_ts"], t["symbol"]))[:MAX_SIGNALS_PER_DAY])
    return trades

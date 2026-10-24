"""Pre-registered intraday setups v0 (docs/architecture/equity_intel_intraday_setups_preregistration_DRAFT.md).

Pure functions over closed 5-minute bars of ONE session. No I/O, no broker path.
Conventions (fixed here, before any result exists):
- bars[i].ts is the bar START time in IST; the trigger time is the bar CLOSE time (start + 5 min).
- A rule sees only bars[0..i] (closed bars). A zero-volume bar, or a gap in the 5-minute grid
  before the trigger bar, means the setup does NOT trigger for that session.
- Each function returns the index of the trigger bar, or None. At most one trigger per session.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional, Sequence

BAR = timedelta(minutes=5)
SESSION_START = time(9, 15)

# P1-P6, frozen 2026-10-24 (preregistration Section 3).
P1_N_OR = 3
P2_ORB_END = time(11, 30)
P4_B_VWAP_MIN = 12
P5_LAST_SIGNAL = time(14, 45)
PDH_EARLIEST = time(9, 30)
SETUP_VERSION = "v0"


@dataclass(frozen=True)
class Bar:
    ts: datetime  # bar start, IST
    o: float
    h: float
    l: float
    c: float
    v: float

    @property
    def close_time(self) -> time:
        return (self.ts + BAR).time()


def _clean_prefix(bars: Sequence[Bar], i: int) -> bool:
    """Session starts at 09:15 and bars[0..i] sit on an unbroken 5-minute grid."""
    if i >= len(bars) or bars[0].ts.time() != SESSION_START:
        return False
    return all(bars[k].ts - bars[k - 1].ts == BAR for k in range(1, i + 1))


def orb_long(bars: Sequence[Bar], n_or: int = P1_N_OR, t_end: time = P2_ORB_END) -> Optional[int]:
    if len(bars) <= n_or or not _clean_prefix(bars, n_or - 1):
        return None
    if any(not b.v for b in bars[:n_or]):
        return None
    or_high = max(b.h for b in bars[:n_or])
    or_low = min(b.l for b in bars[:n_or])
    if or_high - or_low <= 0:
        return None
    for i in range(n_or, len(bars)):
        b = bars[i]
        if not _clean_prefix(bars, i):
            return None
        if b.close_time > t_end:
            return None
        if b.v and b.c > or_high:
            return i
    return None


def vwap_reclaim_long(bars: Sequence[Bar], prev_close: Optional[float], b_min: int = P4_B_VWAP_MIN,
                      last: time = P5_LAST_SIGNAL) -> Optional[int]:
    if prev_close is None:
        return None
    cum_pv = cum_v = 0.0
    prev_bar_below = None  # was previous bar's close <= its session VWAP
    for i, b in enumerate(bars):
        if not _clean_prefix(bars, i):
            return None
        if not b.v:
            return None
        cum_pv += (b.h + b.l + b.c) / 3.0 * b.v
        cum_v += b.v
        vwap = cum_pv / cum_v
        if b.close_time > last:
            return None
        if i >= b_min and prev_bar_below and b.c > vwap and b.c > prev_close:
            return i
        prev_bar_below = b.c <= vwap
    return None


def pdh_break_long(bars: Sequence[Bar], prev_high: Optional[float], earliest: time = PDH_EARLIEST,
                   last: time = P5_LAST_SIGNAL) -> Optional[int]:
    if prev_high is None:
        return None
    for i, b in enumerate(bars):
        if not _clean_prefix(bars, i):
            return None
        if b.close_time > last:
            return None
        if b.close_time >= earliest and b.v and b.c > prev_high:
            return i
    return None


# ---- Round 2 (docs/architecture/equity_intel_intraday_setups_v1_preregistration.md) ----
GAP_MIN, GAP_MAX = 1.01, 1.04
GAP_GO_END = time(10, 30)
DIP_VWAP_FACTOR = 0.985
DIP_MIN_BAR = 6
DIP_END = time(13, 30)
LATE_TIME = time(13, 30)
LATE_MIN_GAIN = 1.015
LATE_NEAR_HIGH = 0.997


def gap_go_long(bars: Sequence[Bar], prev_close: Optional[float]) -> Optional[int]:
    if prev_close is None or not bars or not _clean_prefix(bars, 0):
        return None
    if not (GAP_MIN * prev_close <= bars[0].o <= GAP_MAX * prev_close):
        return None
    return orb_long(bars, P1_N_OR, GAP_GO_END)


def dip_reversal_long(bars: Sequence[Bar]) -> Optional[int]:
    cum_pv = cum_v = 0.0
    for i, b in enumerate(bars):
        if not _clean_prefix(bars, i) or not b.v:
            return None
        cum_pv += (b.h + b.l + b.c) / 3.0 * b.v
        cum_v += b.v
        if b.close_time > DIP_END:
            return None
        if i >= DIP_MIN_BAR and i >= 1:
            vwap = cum_pv / cum_v
            prev = bars[i - 1]
            if prev.c <= vwap * DIP_VWAP_FACTOR and b.c > b.o and b.c > prev.h:
                return i
    return None


def late_strength_long(bars: Sequence[Bar], prev_close: Optional[float]) -> Optional[int]:
    if prev_close is None:
        return None
    hi = 0.0
    for i, b in enumerate(bars):
        if not _clean_prefix(bars, i) or not b.v:
            return None
        hi = max(hi, b.h)
        if b.close_time == LATE_TIME:
            ok = b.c >= prev_close * LATE_MIN_GAIN and b.c >= hi * LATE_NEAR_HIGH
            return i if ok else None
        if b.close_time > LATE_TIME:
            return None
    return None


SETUPS = {"ORB_LONG": "orb", "VWAP_RECLAIM_LONG": "vwap", "PDH_BREAK_LONG": "pdh"}
ROUND2_SETUPS = ["GAP_GO_LONG", "DIP_REVERSAL_LONG", "LATE_STRENGTH_LONG"]


def find_trigger(setup: str, bars: Sequence[Bar], prev_close: Optional[float], prev_high: Optional[float]) -> Optional[int]:
    if setup == "ORB_LONG":
        return orb_long(bars)
    if setup == "VWAP_RECLAIM_LONG":
        return vwap_reclaim_long(bars, prev_close)
    if setup == "PDH_BREAK_LONG":
        return pdh_break_long(bars, prev_high)
    if setup == "GAP_GO_LONG":
        return gap_go_long(bars, prev_close)
    if setup == "DIP_REVERSAL_LONG":
        return dip_reversal_long(bars)
    if setup == "LATE_STRENGTH_LONG":
        return late_strength_long(bars, prev_close)
    raise ValueError(f"unknown setup {setup!r}")

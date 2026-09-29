"""Per-instrument raw features from one instrument's bars. Pure, no I/O."""
from __future__ import annotations

from typing import Sequence

from equity_intel.contracts.features import FeatureSet
from equity_intel.contracts.quality import DataQualityResult, DataStatus
from equity_intel.features.breaks import find_last_break
from equity_intel.features.config import IndicatorConfig
from equity_intel.indicators.context import atr_percent, average_true_range
from equity_intel.indicators.momentum import rate_of_change, relative_strength_index
from equity_intel.indicators.structure import distance_from_high, rolling_high
from equity_intel.indicators.trend import exponential_moving_average
from equity_intel.indicators.volume import relative_volume


def compute_instrument(
    instrument_id: str,
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], volumes: Sequence[float],
    cfg: IndicatorConfig,
) -> tuple[DataQualityResult, FeatureSet, dict]:
    """Break-detect, truncate at the most recent break, compute features.

    Returns (quality, features, detail). Flagged stocks stay in the universe;
    features whose lookback exceeds the post-break bar count come out None.
    prior_high_short, ema_medium_lag and relative_return are left None: the
    design fixes no window/lag for the first two and E4 fetches no benchmark.
    """
    detail: dict = {"break_date_index": None, "break_ratio": None}
    brk = find_last_break(closes, cfg.break_low_ratio, cfg.break_high_ratio)
    start = brk.index if brk else 0
    if brk:
        detail.update(break_date_index=brk.index, break_ratio=brk.ratio)
    h, l, c, v = highs[start:], lows[start:], closes[start:], volumes[start:]
    n = len(c)

    def ema_last(period: int):
        series = exponential_moving_average(c, period)
        return series[-1] if series else None

    recent_v = list(v[-cfg.volume_usable_window:])
    usable = sum(1 for x in recent_v if x and x > 0)
    volume_ok = len(recent_v) == cfg.volume_usable_window and usable >= cfg.volume_usable_bars
    detail["volume_usable"] = volume_ok
    rvol = relative_volume(v[-1], list(v[-(cfg.rvol_window + 1):-1])) if n > cfg.rvol_window and volume_ok else None

    high_window = rolling_high(h, cfg.high_window, exclude_current=False)
    features = FeatureSet(
        instrument_id=instrument_id, n_bars=n, w52_complete=n >= cfg.high_window,
        ema_short=ema_last(cfg.ema_short), ema_medium=ema_last(cfg.ema_medium), ema_long=ema_last(cfg.ema_long),
        rsi=relative_strength_index(c, cfg.rsi_period), roc=rate_of_change(c, cfg.roc_lookback),
        relative_volume=rvol,
        distance_from_high=distance_from_high(c[-1], high_window) if high_window else None,
        prior_high_long=high_window,
        atr_percent=atr_percent(average_true_range(h, l, c, cfg.atr_period), c[-1]) if n else None,
    )
    if n < cfg.minimum_history_bars:
        status = DataStatus.INSUFFICIENT_HISTORY
        reason = f"{n} post-break bars; {cfg.minimum_history_bars} required" if brk else f"{n} bars; {cfg.minimum_history_bars} required"
    else:
        status, reason = DataStatus.VALID, None
    if brk:
        note = f"possible corporate-action break at bar index {brk.index}, close ratio {brk.ratio:.4f}"
        reason = f"{reason}; {note}" if reason else note
    return DataQualityResult(status, reason), features, detail

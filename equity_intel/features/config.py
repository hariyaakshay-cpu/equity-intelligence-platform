"""Indicator display parameters (design Section 11, decision 10).

One explicit config, no code defaults. Values are recorded on every scan
run and are provisional, not B2-authoritative. No band, cutoff, or score
is derived from them.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndicatorConfig:
    ema_short: int
    ema_medium: int
    ema_long: int
    rsi_period: int
    roc_lookback: int
    relative_return_lookback: int
    rvol_window: int
    high_window: int
    atr_period: int
    minimum_history_bars: int
    minimum_universe_count: int
    volume_usable_bars: int
    volume_usable_window: int
    break_low_ratio: float
    break_high_ratio: float
    label: str = "provisional, not B2-authoritative"

    def as_dict(self) -> dict:
        return asdict(self)


def load_config(path: str | Path) -> IndicatorConfig:
    return IndicatorConfig(**json.loads(Path(path).read_text(encoding="utf-8")))

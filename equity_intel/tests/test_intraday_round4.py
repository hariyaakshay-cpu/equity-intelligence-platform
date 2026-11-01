"""Synthetic-data tests for the round-4 setups (no market data, no network)."""
from datetime import datetime, timedelta

from equity_intel.intraday.round4 import gap_volume_long, highvol_orb_long
from equity_intel.intraday.setups import Bar


def _bars(n=75, base=100.0, vol=1000.0, overrides=None, day="2026-01-05"):
    start = datetime.fromisoformat(f"{day}T09:15:00+05:30")
    out = []
    for i in range(n):
        o = h = l = c = base
        v = vol
        if overrides and i in overrides:
            o, h, l, c, v = overrides[i]
        out.append(Bar(start + timedelta(minutes=5 * i), o, h, l, c, v))
    return out


def test_highvol_orb_needs_top_bucket_and_width():
    wide = {1: (100, 101, 99, 100, 1000), 3: (100, 102, 100, 102, 1000)}  # OR 99-101 (2% wide); bar 3 breaks out
    assert highvol_orb_long(_bars(overrides=wide), True) == 3
    assert highvol_orb_long(_bars(overrides=wide), False) is None
    narrow = {1: (100, 100.3, 99.9, 100, 1000), 3: (100, 101, 100, 101, 1000)}  # OR width 0.4% < 0.6%
    assert highvol_orb_long(_bars(overrides=narrow), True) is None


def test_gap_volume_needs_gap_volume_and_breakout():
    gap = {0: (102.5, 103, 102.5, 103, 3000), 1: (103, 103.2, 102.8, 103, 3000), 2: (103, 103.5, 102.9, 103, 3000),
           3: (103, 104.5, 103, 104.5, 1000)}
    assert gap_volume_long(_bars(base=103.0, overrides=gap), 100.0, 3000.0) == 3
    assert gap_volume_long(_bars(base=103.0, overrides=gap), 100.0, 6000.0) is None  # first-3 volume under 2x the baseline
    assert gap_volume_long(_bars(base=103.0, overrides=gap), 102.0, 3000.0) is None  # gap under 2%

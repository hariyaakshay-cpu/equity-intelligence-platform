"""PROVISIONAL v0 component scorers (Momentum, Relative Strength, Volume,
Structure-distance). Pure functions of a FeatureSet; no I/O.

Rules (B2 invariant I6): a component that cannot be legitimately computed is
None, never 0. Momentum needs BOTH RSI and ROC; if either is None the
component is None (no partial sum) - an assumption consistent with D07.

Trend and the Structure breakout add-on use the features added in step 2b
(close, EMA50 lag, 20/50-bar prior highs). The fifth Trend test is an
ASSUMPTION (see provisional_v0.TREND_FIFTH_TEST_IS_ASSUMED).
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from equity_intel.contracts.features import FeatureSet
from equity_intel.contracts.scoring import ComponentResult, CompositeResult
from equity_intel.scoring import provisional_v0 as cfg

Bands = Sequence[Tuple[float, int]]


def _band(value: float, bands: Bands, top: int, first_inclusive: bool = False) -> int:
    for i, (edge, points) in enumerate(bands):
        inclusive = first_inclusive and i == 0
        if value < edge or (inclusive and value <= edge):
            return points
    return top


def _none(name: str, why: str) -> ComponentResult:
    return ComponentResult(component_name=name, score=None, basis=why)


def momentum(f: FeatureSet) -> ComponentResult:
    if f.rsi is None or f.roc is None:
        return _none("momentum", "rsi or roc unavailable")
    rsi_pts = _band(f.rsi, cfg.RSI_BANDS, cfg.RSI_TOP)
    roc_pts = _band(f.roc, cfg.ROC_BANDS, cfg.ROC_TOP, cfg.ROC_FIRST_EDGE_INCLUSIVE)
    return ComponentResult("momentum", rsi_pts + roc_pts, f"rsi={rsi_pts} roc={roc_pts}")


def relative_strength(f: FeatureSet) -> ComponentResult:
    if f.relative_return is None:
        return _none("relative_strength", "relative_return unavailable")
    return ComponentResult("relative_strength", _band(f.relative_return, cfg.RS_BANDS, cfg.RS_TOP), "rp60")


def volume(f: FeatureSet) -> ComponentResult:
    if f.relative_volume is None:
        return _none("volume", "relative_volume unavailable or volume unusable")
    return ComponentResult("volume", _band(f.relative_volume, cfg.RVOL_BANDS, cfg.RVOL_TOP), "rvol20")


def structure_distance_points(f: FeatureSet) -> Optional[int]:
    """Distance-from-52-week-high part of Structure (0-12). None when the
    52-week window is incomplete (no fallback, D05).
    """
    if not f.w52_complete or f.distance_from_high is None:
        return None
    return _band(f.distance_from_high, cfg.DIST52_BANDS, cfg.DIST52_TOP)


def structure_breakout_points(f: FeatureSet) -> Optional[int]:
    """Breakout add-on (0/4/8). None if close or either prior high is missing."""
    if not f.w52_complete or None in (f.close, f.prior_high_short, f.prior_high_medium):
        return None
    if f.close > f.prior_high_medium:
        return cfg.BREAKOUT_MEDIUM_POINTS
    if f.close > f.prior_high_short:
        return cfg.BREAKOUT_SHORT_POINTS
    return 0


def structure(f: FeatureSet) -> ComponentResult:
    dist, brk = structure_distance_points(f), structure_breakout_points(f)
    if dist is None or brk is None:
        return _none("structure", "52-week window incomplete or prior highs/close unavailable")
    return ComponentResult("structure", dist + brk, f"dist52={dist} breakout={brk}")


def trend(f: FeatureSet) -> ComponentResult:
    needed = (f.close, f.ema_short, f.ema_medium, f.ema_long, f.ema_medium_lag)
    if None in needed:
        return _none("trend", "needs close, EMA20/50/200 and EMA50 lag (>=200 bars)")
    tests = (
        f.close > f.ema_short,
        f.close > f.ema_medium,
        f.ema_medium > f.ema_long,
        f.ema_medium > f.ema_medium_lag,
        f.ema_short > f.ema_medium,  # ASSUMED fifth test
    )
    passed = sum(tests)
    return ComponentResult("trend", passed * cfg.TREND_POINTS_PER_TEST, f"{passed}/5 tests")


def score_instrument(f: FeatureSet) -> CompositeResult:
    """Provisional v0 composite: exact sum of five components, None if ANY is None."""
    comps = (trend(f), momentum(f), relative_strength(f), volume(f), structure(f))
    total = None if any(r.score is None for r in comps) else sum(r.score for r in comps)
    return CompositeResult(instrument_id=f.instrument_id, components=comps, composite=total)


def horizon_scores(f: FeatureSet) -> dict:
    """Short and medium horizon scores as 0-100 percentages of each horizon's
    own maximum (see provisional_v0). None if any needed part is None - no
    partial sum. Same inputs and rules as the five components.
    """
    t, m = trend(f).score, momentum(f).score
    r, v = relative_strength(f).score, volume(f).score
    dist, brk = structure_distance_points(f), structure_breakout_points(f)

    def pct(parts, maximum):
        return None if None in parts else int(100.0 * sum(parts) / maximum + 0.5)

    return {"short": pct((m, v, brk), cfg.SHORT_MAX), "medium": pct((t, r, dist), cfg.MEDIUM_MAX)}

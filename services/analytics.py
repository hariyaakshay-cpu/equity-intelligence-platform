"""Price-based analytics: returns, moving averages, RSI, volatility, 52-week range."""

from typing import Optional

import pandas as pd

TRADING_DAYS = 252
RETURN_WINDOWS = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252}


def _round(x) -> Optional[float]:
    return None if x is None or pd.isna(x) else round(float(x), 4)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def compute_indicators(closes: pd.Series) -> dict:
    """
    Compute indicators from daily closes.

    Args:
        closes: Close prices indexed by date, oldest first.

    Returns:
        Dict of latest indicator values; entries are None when there is
        not enough history for them.
    """
    closes = closes.astype(float).sort_index()
    n = len(closes)
    if n == 0:
        return {"observations": 0}

    last = closes.iloc[-1]
    daily = closes.pct_change()
    window = closes.iloc[-TRADING_DAYS:]

    result = {
        "observations": n,
        "as_of": str(closes.index[-1]),
        "close": _round(last),
        "returns": {
            label: _round(last / closes.iloc[-d - 1] - 1) if n > d else None
            for label, d in RETURN_WINDOWS.items()
        },
        "sma_20": _round(closes.rolling(20).mean().iloc[-1]),
        "sma_50": _round(closes.rolling(50).mean().iloc[-1]),
        "sma_200": _round(closes.rolling(200).mean().iloc[-1]),
        "ema_20": _round(closes.ewm(span=20, min_periods=20, adjust=False).mean().iloc[-1]),
        "rsi_14": _round(rsi(closes).iloc[-1]),
        "volatility_30d_annualized": _round(daily.rolling(30).std().iloc[-1] * TRADING_DAYS**0.5)
        if n > 30 else None,
        "high_52w": _round(window.max()),
        "low_52w": _round(window.min()),
        "pct_from_52w_high": _round(last / window.max() - 1),
    }
    return result

"""Paced Upstox price acquisition.

Per docs/architecture/equity_intel_scanner_v1_spec.md Section 9: pace at
~5 requests/second; retry 429, timeouts, and 5xx up to 3 times with
backoff; other 4xx fails that symbol only (FAILED, reason recorded);
retries exhausted -> that symbol FAILED; a 401 aborts the run.

Retry is deliberately NOT reimplemented in this module.
core.providers.upstox_provider.UpstoxProvider._make_api_request already
wraps every call in @retry(stop_after_attempt(3),
wait_exponential(...), retry_if_exception_type((ProviderConnectionError,
ProviderAPIError))) -- connection errors, timeouts, and every non-401 HTTP
status (429, 5xx, and any other 4xx) all surface as one of those two
exception types and are therefore already retried up to 3 times with
backoff by the provider itself, before this module ever sees the final
exception. This task's instructions say to reuse the existing provider
and its token handling unmodified; adding a second retry loop here around
an already-3x-retried call would silently multiply the effective attempt
count past 3, not honor it. This module's job is: pace the *rate* of
per-symbol calls (the provider has no rate limiter at all), translate a
401 into a whole-run abort, and turn any other terminal failure into a
per-symbol FAILED outcome with a reason -- never into an
uncaught exception that would stop the rest of the universe.
"""
from __future__ import annotations

import time as time_module
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from core.providers.upstox_provider import (
    AuthenticationError,
    InvalidIntervalError,
    InvalidSymbolError,
    ProviderError,
)

DEFAULT_REQUESTS_PER_SECOND = 5.0


class AuthFailedError(RuntimeError):
    """A 401 from the price vendor. The caller must abort the whole
    ScanRun (abort_reason=AUTH_FAILED), not just this one symbol."""


@dataclass
class RateLimiter:
    """Paces calls to roughly `requests_per_second`, across this
    scanner's own acquisition loop. Sleeps just enough between
    consecutive wait() calls to keep the interval between them at or
    above 1/requests_per_second; a fresh limiter's first wait() never
    sleeps."""

    requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND
    _last_call_at: Optional[float] = field(default=None, init=False, repr=False)

    def wait(self) -> None:
        min_interval = 1.0 / self.requests_per_second
        now = time_module.monotonic()
        if self._last_call_at is not None:
            remaining = min_interval - (now - self._last_call_at)
            if remaining > 0:
                time_module.sleep(remaining)
        self._last_call_at = time_module.monotonic()


def fetch_symbol_candles(
    provider,
    instrument_key: str,
    start_date: datetime,
    end_date: datetime,
) -> Tuple[List, Optional[str]]:
    """Fetch one symbol's (or the benchmark's) daily candles.

    Returns:
        (candles, error): on success, candles is the provider's returned
        list (possibly empty) and error is None. On a per-symbol failure,
        candles is [] and error is a short human-readable reason.

    Raises:
        AuthFailedError: on a 401. Never returned as a per-symbol error --
            the caller must treat this as a whole-run abort.
    """
    try:
        candles = provider.get_historical_data(instrument_key, "1day", start_date, end_date)
        return candles, None
    except AuthenticationError as exc:
        raise AuthFailedError(str(exc)) from exc
    except (InvalidSymbolError, InvalidIntervalError, ProviderError) as exc:
        return [], str(exc)


def fetch_universe_candles(
    provider,
    instrument_keys_by_symbol: dict,
    start_date: datetime,
    end_date: datetime,
    rate_limiter: Optional[RateLimiter] = None,
) -> dict:
    """Fetch candles for every symbol in `instrument_keys_by_symbol`
    (symbol -> instrument_key), paced by `rate_limiter`.

    One bad symbol never aborts the whole scan (Section 9) -- every
    symbol's (candles, error) tuple is collected and returned, even
    when error is not None; only AuthFailedError propagates (uncaught),
    since a 401 aborts the whole run rather than being recorded
    per-symbol.

    Returns:
        dict[symbol] -> (candles, error), same shape as
        fetch_symbol_candles's return value, one entry per input symbol.
    """
    limiter = rate_limiter or RateLimiter()
    results = {}
    for symbol, instrument_key in instrument_keys_by_symbol.items():
        limiter.wait()
        results[symbol] = fetch_symbol_candles(provider, instrument_key, start_date, end_date)
    return results

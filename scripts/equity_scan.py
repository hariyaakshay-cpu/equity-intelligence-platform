"""Equity Intelligence Scanner V1 -- CLI entry point.

Runs the full pipeline from docs/architecture/equity_intel_scanner_v1_spec.md
Section 1: Universe -> Calendar -> Price acquisition -> Candle validation ->
Immutable snapshots -> Symbol classification + review flags -> ScanRun
completion. B2 scoring is out of scope and always BLOCKED_B2.

Writes ONLY to the canonical database (equity_intel/scanner/db.py refuses
every other path, including the demo database). Every abort path
(CALENDAR_INVALID, AUTH_FAILED, INSTRUMENT_MASTER_UNAVAILABLE,
INSTRUMENT_MAP_EMPTY, CORPORATE_ACTION_REVIEW_CSV_INVALID, and
INTERRUPTED for a leftover RUNNING row from a previous process) ends the
run ABORTED with that reason recorded, never a silent partial write.

One symbol's failure is isolated: any exception while validating,
snapshotting, classifying, or writing that symbol's own result rolls back
only that symbol's uncommitted work and records it FAILED with the
exception as status_reason -- it never aborts the run. The one exception
is auth: AUTH_FAILURE_ABORT_THRESHOLD consecutive per-symbol 401s abort the
run (AUTH_FAILURE), since a dead token is a whole-run condition.

Before any ScanRun row exists, a pre-flight probe checks the Upstox token
(one cheap call); a bad token exits non-zero with no row created. Any
exception escaping the pipeline after the row exists ends it ABORTED
(UNEXPECTED_ERROR, or INTERRUPTED for KeyboardInterrupt/SystemExit) and is
then re-raised -- a row is never left stuck RUNNING by this process.

Only one scan may run at a time: data/equity_intel_scan.lock is created
at start and removed at the end (including on abort or an uncaught
exception); a second concurrent invocation refuses to start rather than
racing the first, or worse, marking the first run's still-RUNNING row
INTERRUPTED.

Usage:
    python scripts/equity_scan.py                        # full universe
    python scripts/equity_scan.py --symbols RELIANCE,TCS,INFY   # smoke run
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import Settings
from core.providers.upstox_provider import UpstoxProvider
from equity_intel.config import AUTH_FAILURE_ABORT_THRESHOLD, IST, PRICE_FETCH_LOOKBACK_DAYS, REQUIRED_SESSIONS
from equity_intel.persistence import connection as db_connection
from equity_intel.scanner import classification, execution_guard, scan_run
from equity_intel.scanner import db as scanner_db
from equity_intel.scanner.acquisition import AuthFailedError, RateLimiter, fetch_symbol_candles, preflight_token_check
from equity_intel.scanner.acquisition import AUTH_FAILED, AUTH_FAILURE
from equity_intel.scanner.candle_validation import validate_candle
from equity_intel.scanner.candle_validation import VALID as CANDLE_VALID
from equity_intel.scanner.corporate_actions import (
    CORPORATE_ACTION_REVIEW_CSV_INVALID,
    CorporateActionReviewCSVInvalidError,
    is_under_review,
    load_corporate_action_review,
)
from equity_intel.scanner.instrument_mapping import INSTRUMENT_MAP_EMPTY, map_universe_isins, record_instrument_map_provenance
from equity_intel.scanner.instrument_master import (
    INSTRUMENT_MASTER_UNAVAILABLE,
    InstrumentMasterUnavailableError,
    fetch_instrument_master,
)
from equity_intel.scanner.scan_lock import ScannerAlreadyRunningError, acquire_scan_lock, release_scan_lock
from equity_intel.scanner.snapshots import quantize_price, write_snapshot
from equity_intel.scanner.trading_calendar import (
    BENCHMARK_INSTRUMENT_KEY,
    CALENDAR_INVALID,
    CalendarInvalidError,
    fetch_and_build_calendar,
)
from equity_intel.scanner.universe import load_universe

DATA_REFERENCE_DIR = REPO_ROOT / "data" / "reference"
CORPORATE_ACTION_REVIEW_CSV = DATA_REFERENCE_DIR / "corporate_action_review.csv"
LOCK_PATH = REPO_ROOT / "data" / "equity_intel_scan.lock"


def _find_universe_csv() -> Path:
    candidates = sorted(DATA_REFERENCE_DIR.glob("nifty500_constituents_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"no nifty500_constituents_*.csv found under {DATA_REFERENCE_DIR}")
    return candidates[-1]


def generate_run_id(now: datetime) -> str:
    return f"scan_{now.strftime('%Y%m%dT%H%M%S')}"


def _candle_trading_date(candle) -> str:
    ts = candle.timestamp
    return ts.date().isoformat() if isinstance(ts, datetime) else ts.isoformat()


def _run_scan_locked(*, symbols_filter=None, now=None) -> int:
    now = now or datetime.now(IST)
    run_id = generate_run_id(now)

    universe = load_universe(_find_universe_csv())
    if symbols_filter:
        requested = set(symbols_filter)
        members = [m for m in universe.members if m.symbol in requested]
        unknown = requested - {m.symbol for m in members}
        if unknown:
            print(f"Warning: not in the universe (skipped): {sorted(unknown)}")
        if not members:
            print(f"Error: none of the requested --symbols matched the universe: {sorted(requested)}")
            return 1
    else:
        members = universe.members

    # Pre-flight: everything that can fail on a bad/missing/expired token
    # happens BEFORE start_scan_run, so it leaves no scan_runs row behind.
    token = None
    try:
        settings = Settings()
        token = getattr(settings, "UPSTOX_ACCESS_TOKEN", None)
        provider = UpstoxProvider(settings)
        preflight_token_check(provider, BENCHMARK_INSTRUMENT_KEY, now)
    except AuthFailedError:
        print("Pre-flight failed: Upstox rejected the access token (401). Refresh UPSTOX_ACCESS_TOKEN and re-run. No scan run was started.")
        return 1
    except Exception as exc:
        print(f"Pre-flight failed: {_error_summary(exc, token)}. No scan run was started.")
        return 1

    conn = scanner_db.get_scan_connection()
    db_connection.initialize_schema(conn)

    scan_run.start_scan_run(
        conn,
        run_id=run_id,
        requested_symbols=len(members),
        price_source="upstox",
        symbols_filter=symbols_filter,
        now=now,
    )

    # Everything after start_scan_run: any escape (other than the explicit
    # abort paths inside _execute_scan, which already wrote ABORTED) must
    # not leave the row stuck RUNNING.
    try:
        return _execute_scan(
            conn, run_id=run_id, universe=universe, members=members, provider=provider, now=now
        )
    except BaseException as exc:
        reason = scan_run.UNEXPECTED_ERROR if isinstance(exc, Exception) else scan_run.INTERRUPTED
        _abort_on_escape(conn, run_id, reason, _error_summary(exc, token))
        raise


def _error_summary(exc: BaseException, token: Optional[str] = None, limit: int = 500) -> str:
    """`Type: message`, token redacted, truncated -- safe to store and print."""
    text = f"{type(exc).__name__}: {exc}"
    if token:
        text = text.replace(token, "[REDACTED]")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _abort_on_escape(conn, run_id: str, reason: str, summary: str) -> None:
    """Best-effort ABORTED write for an escaping exception. Must never
    raise: the original exception is what the caller re-raises, and a
    failure here (closed connection, locked DB) must not mask it."""
    try:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            aborted = scan_run.abort_scan_run_if_running(
                conn, run_id=run_id, abort_reason=reason, errors=[summary], now=datetime.now(IST)
            )
        except Exception:
            # The connection itself may be closed/broken -- retry on a fresh one.
            fresh = scanner_db.get_scan_connection()
            try:
                aborted = scan_run.abort_scan_run_if_running(
                    fresh, run_id=run_id, abort_reason=reason, errors=[summary], now=datetime.now(IST)
                )
            finally:
                fresh.close()
        if aborted:
            print(f"run_id={run_id} status=ABORTED abort_reason={reason}: {summary}", file=sys.stderr)
    except Exception as write_exc:
        print(
            f"run_id={run_id} could not be marked ABORTED ({type(write_exc).__name__}); "
            f"it will be marked INTERRUPTED by the next scan start",
            file=sys.stderr,
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _execute_scan(conn, *, run_id, universe, members, provider, now) -> int:
    def abort(reason: str, detail: str) -> int:
        scan_run.abort_scan_run(conn, run_id=run_id, abort_reason=reason, errors=[detail], now=datetime.now(IST))
        conn.close()
        print(f"run_id={run_id} status=ABORTED abort_reason={reason}: {detail}")
        return 1

    try:
        review = load_corporate_action_review(CORPORATE_ACTION_REVIEW_CSV)
    except CorporateActionReviewCSVInvalidError as exc:
        return abort(CORPORATE_ACTION_REVIEW_CSV_INVALID, str(exc))

    rate_limiter = RateLimiter()

    window_end = now
    window_start = now - timedelta(days=PRICE_FETCH_LOOKBACK_DAYS)
    window_start_date = window_start.date().isoformat()
    window_end_date = window_end.date().isoformat()

    try:
        calendar = fetch_and_build_calendar(provider, start_date=window_start, end_date=window_end, now=now)
    except AuthFailedError as exc:
        return abort(AUTH_FAILED, str(exc))
    except CalendarInvalidError as exc:
        return abort(CALENDAR_INVALID, str(exc))

    try:
        master = fetch_instrument_master(DATA_REFERENCE_DIR, now=now)
    except InstrumentMasterUnavailableError as exc:
        return abort(INSTRUMENT_MASTER_UNAVAILABLE, str(exc))

    universe_isins = [m.isin for m in members]
    mapping, provenance = map_universe_isins(master, universe_isins)
    record_instrument_map_provenance(conn, run_id=run_id, provenance=provenance)
    conn.commit()
    if provenance.is_empty:
        return abort(INSTRUMENT_MAP_EMPTY, f"0 of {len(universe_isins)} universe ISINs matched the instrument master")

    window_sessions = classification.compute_window_sessions(
        calendar.calendar_dates, calendar.latest_closed_session, REQUIRED_SESSIONS
    )

    status_counts = {classification.FAILED: 0, classification.INSUFFICIENT_HISTORY: 0, classification.STALE: 0, classification.VALID: 0}
    flag_counts = {"HISTORY_GAPS": 0, "NON_EQ_SERIES": 0, "PRICE_BREAK_DETECTED": 0, "CORPORATE_ACTION_REVIEW": 0}
    successful_symbols = 0
    failed_symbols = 0
    consecutive_auth_failures = 0

    def record_failed(member, reason: str) -> None:
        nonlocal failed_symbols
        classification.write_symbol_scan_result(
            conn,
            scan_run_id=run_id,
            symbol=member.symbol,
            instrument_key=mapping.isin_to_instrument_key.get(member.isin),
            isin=member.isin,
            series=member.series,
            company_name=member.company_name,
            sector=member.sector,
            symbol_data_status=classification.FAILED,
            status_reason=reason,
            available_session_count=None,
            missing_session_count=None,
            non_eq_series_flag=member.non_eq_series_flag,
        )
        conn.commit()
        failed_symbols += 1
        status_counts[classification.FAILED] += 1
        if member.non_eq_series_flag:
            flag_counts["NON_EQ_SERIES"] += 1

    for member in members:
        instrument_key = mapping.isin_to_instrument_key.get(member.isin)
        if instrument_key is None:
            record_failed(member, f"no instrument-master match for ISIN {member.isin}")
            continue

        rate_limiter.wait()
        try:
            candles, error = fetch_symbol_candles(provider, instrument_key, window_start, window_end)
            consecutive_auth_failures = 0
        except AuthFailedError as exc:
            # Auth circuit breaker: one 401 fails this symbol only; N in a
            # row (any non-auth fetch outcome resets the count) means the
            # token is dead -- abort instead of FAILing every remaining symbol.
            consecutive_auth_failures += 1
            if consecutive_auth_failures >= AUTH_FAILURE_ABORT_THRESHOLD:
                return abort(
                    AUTH_FAILURE,
                    f"{consecutive_auth_failures} consecutive auth failures (last symbol {member.symbol}); "
                    f"{failed_symbols} symbols already recorded FAILED",
                )
            record_failed(member, "auth failure (401)")
            continue

        if error is not None:
            record_failed(member, error)
            continue

        # Everything from here on -- structural validation, snapshot
        # writes, classification, and the final symbol_scan_results write
        # -- is one unit for this symbol: any exception anywhere in it
        # rolls back only this symbol's uncommitted writes and records it
        # FAILED, rather than crashing the whole run or corrupting
        # another symbol's data.
        try:
            fetched_at = datetime.now(IST).isoformat()
            valid_dates = []
            valid_closes_by_date = {}
            for candle in candles:
                trading_date = _candle_trading_date(candle)
                status, errors = validate_candle(candle.open, candle.high, candle.low, candle.close, candle.volume)
                write_snapshot(
                    conn,
                    scan_run_id=run_id,
                    symbol=member.symbol,
                    trading_date=trading_date,
                    source="upstox",
                    fetched_at_ist=fetched_at,
                    open_=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    candle_validation_status=status,
                    validation_errors=errors or None,
                )
                if status == CANDLE_VALID:
                    valid_dates.append(trading_date)
                    valid_closes_by_date[trading_date] = quantize_price(candle.close)

            result = classification.classify_symbol(
                valid_trading_dates=valid_dates,
                window_sessions=window_sessions,
                latest_closed_session=calendar.latest_closed_session,
            )
            closes_in_order = [valid_closes_by_date[d] for d in sorted(valid_closes_by_date)]
            price_break = classification.detect_price_break(closes_in_order)
            corp_flag = is_under_review(review, member.symbol, window_start_date, window_end_date)

            classification.write_symbol_scan_result(
                conn,
                scan_run_id=run_id,
                symbol=member.symbol,
                instrument_key=instrument_key,
                isin=member.isin,
                series=member.series,
                company_name=member.company_name,
                sector=member.sector,
                symbol_data_status=result.symbol_data_status,
                status_reason=result.status_reason,
                available_session_count=result.available_session_count,
                missing_session_count=result.missing_session_count,
                history_gaps_flag=result.history_gaps_flag,
                corporate_action_review_flag=corp_flag,
                price_break_detected_flag=price_break,
                non_eq_series_flag=member.non_eq_series_flag,
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            record_failed(member, str(exc))
            continue

        successful_symbols += 1
        status_counts[result.symbol_data_status] += 1
        if result.history_gaps_flag:
            flag_counts["HISTORY_GAPS"] += 1
        if member.non_eq_series_flag:
            flag_counts["NON_EQ_SERIES"] += 1
        if price_break:
            flag_counts["PRICE_BREAK_DETECTED"] += 1
        if corp_flag:
            flag_counts["CORPORATE_ACTION_REVIEW"] += 1

    scan_run.complete_scan_run(
        conn,
        run_id=run_id,
        universe_version=universe.universe_version,
        corporate_action_review_version=review.version,
        benchmark=BENCHMARK_INSTRUMENT_KEY,
        calendar_source=calendar.calendar_source,
        calendar_verification=calendar.calendar_verification,
        latest_closed_session=calendar.latest_closed_session,
        calendar_dates=calendar.calendar_dates,
        successful_symbols=successful_symbols,
        failed_symbols=failed_symbols,
        status_counts=status_counts,
        flag_counts=flag_counts,
        excluded_symbols=[{"symbol": e.symbol, "reason": e.reason} for e in universe.excluded_symbols],
        now=datetime.now(IST),
    )
    conn.close()

    print(f"run_id={run_id} status=COMPLETE requested={len(members)} successful={successful_symbols} failed={failed_symbols}")
    print(f"status_counts={status_counts}")
    print(f"flag_counts={flag_counts}")
    return 0


def run_scan(*, symbols_filter=None, now=None) -> int:
    """Returns the process exit code (0 on COMPLETE, 1 on ABORTED or refusal)."""
    execution_guard.assert_no_forbidden_modules_loaded()

    try:
        acquire_scan_lock(LOCK_PATH, now=now)
    except ScannerAlreadyRunningError as exc:
        print(str(exc))
        return 1

    try:
        return _run_scan_locked(symbols_filter=symbols_filter, now=now)
    finally:
        release_scan_lock(LOCK_PATH)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the Equity Intelligence Scanner V1.")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols for a smoke run (e.g. RELIANCE,TCS,INFY). Default: the full universe.",
    )
    args = parser.parse_args(argv)
    symbols_filter = (
        {s.strip() for s in args.symbols.split(",") if s.strip()} if args.symbols else None
    )
    return run_scan(symbols_filter=symbols_filter)


if __name__ == "__main__":
    sys.exit(main())

"""Context builder for the Stock Detail page (/equity/stock/<symbol>).

Stage 1 ("can I trust the data?"): everything here is a stored value, a count
of stored rows, or a hash recomputed from stored bars. Nothing is scored,
ranked, charted or recommended, and nothing is computed from prices except the
per-symbol content-hash recheck (which only hashes stored text).

Like queries.py and aggregates.py this module only executes SELECTs on a
connection the caller opened read-only. It never imports sqlite3.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dashboard import aggregates, queries
from dashboard.queries import _fetch_all_dicts, _fetch_one_dict
from equity_intel.config import PRICE_BREAK_HIGH_RATIO, PRICE_BREAK_LOW_RATIO, REQUIRED_SESSIONS
from equity_intel.persistence import db_path_guard
from equity_intel.scanner import corporate_actions
from equity_intel.scanner.snapshots import compute_content_hash_from_stored_row

NOT_RECORDED = "not recorded"

# Layer labels, shown next to every value so ScanRun and E4 counts never look contradictory.
SCANRUN = "ScanRun"
E4 = "E4"

STATUS_HISTORY_LIMIT = 50
OHLCV_ROWS = 30  # newest-first table of this symbol's stored daily bars; table only, no chart


def review_csv_path() -> Path:
    return db_path_guard.REPO_ROOT / "data" / "reference" / "corporate_action_review.csv"


def get_newer_non_complete_run(conn, run: dict) -> Optional[dict]:
    """The newest run started after `run` that is not itself a COMPLETE full
    run: RUNNING, ABORTED, or a COMPLETE --symbols smoke run. Names the
    specific reason and a symbol count."""
    newer = _fetch_one_dict(
        conn,
        "SELECT * FROM scan_runs WHERE started_at > ? AND (status != 'COMPLETE' OR symbols_filter_json IS NOT NULL) "
        "ORDER BY started_at DESC LIMIT 1",
        (run["started_at"],),
    )
    if newer is None:
        return None
    stored = conn.execute(
        "SELECT COUNT(*) FROM symbol_scan_results WHERE scan_run_id = ?", (newer["run_id"],)
    ).fetchone()[0]
    if newer["symbols_filter_json"]:
        symbols = len(json.loads(newer["symbols_filter_json"]))
        reason = f"smoke run (--symbols, {symbols} symbols)"
        count = f"{symbols} symbols requested"
    elif newer["status"] == "ABORTED":
        reason = f"ABORTED ({newer['abort_reason'] or 'no abort reason recorded'})"
        count = _requested_text(newer, stored)
    else:
        reason = "RUNNING (not finished)" if newer["status"] == "RUNNING" else newer["status"]
        count = _requested_text(newer, stored)
    return {"run_id": newer["run_id"], "started_at": newer["started_at"], "reason": reason, "symbols": count}


def _requested_text(run: dict, stored: int) -> str:
    requested = run["requested_symbols"]
    base = f"{requested} symbols requested" if requested is not None else "requested symbol count not recorded"
    return f"{base}; {stored} symbol results stored"


def _check(name, layer, result, rule, rule_status, ok=None):
    """One data-status-check row. `ok` is True/False when a frozen rule gives
    a yes/no from a stored value, None when the row only displays a stored value."""
    return {"name": name, "layer": layer, "result": result, "rule": rule, "rule_status": rule_status, "ok": ok}


def _yes_no(value) -> str:
    return NOT_RECORDED if value is None else ("yes" if value else "no")


def _status_checks(result: dict, run: dict, e4: Optional[dict], quality: Optional[dict], features: Optional[dict]) -> list:
    available = result["available_session_count"]
    missing = result["missing_session_count"]
    failed = result["symbol_data_status"] == "FAILED"
    sessions_rule = f"available valid candles >= {REQUIRED_SESSIONS} (spec section 4)"
    if failed:
        # Acquisition failed, so the window was never evaluated: never a tick or cross.
        stored = NOT_RECORDED if available is None else f"{available} of {REQUIRED_SESSIONS}"
        sessions = _check(f"{REQUIRED_SESSIONS} sessions", SCANRUN,
                          f"not applicable: acquisition failed (stored count: {stored})", sessions_rule, "frozen")
    elif available is None:
        sessions = _check(f"{REQUIRED_SESSIONS} sessions", SCANRUN, NOT_RECORDED, sessions_rule, "frozen")
    else:
        sessions = _check(
            f"{REQUIRED_SESSIONS} sessions", SCANRUN,
            f"{available} of {REQUIRED_SESSIONS} available"
            + (f"; {missing} calendar session(s) with no valid candle" if missing is not None else ""),
            sessions_rule, "frozen", available >= REQUIRED_SESSIONS)

    cfg = e4["config"] if e4 else {}
    ema_period = cfg.get("ema_long")
    e4_missing = "no E4 row for this symbol" if e4 else "no COMPLETE E4 scan"
    if features is not None:
        ema = _check(f"EMA{ema_period or ''} (long)", E4,
                     "stored value present" if features["ema_long"] is not None else "no stored value",
                     "E4 computes the long EMA when enough bars exist", "provisional", features["ema_long"] is not None)
    else:
        ema = _check(f"EMA{ema_period or ''} (long)", E4, f"{NOT_RECORDED} ({e4_missing})",
                     "E4 computes the long EMA when enough bars exist", "provisional")

    if quality is not None:
        w52 = _check("52-week (w52_complete)", E4, _yes_no(bool(quality["w52_complete"])) +
                     f" ({quality['n_bars']} bars stored)", f"bars >= high_window ({cfg.get('high_window', NOT_RECORDED)})",
                     "provisional", bool(quality["w52_complete"]))
        usable = quality["volume_usable"]
        vol = _check("Volume usable", E4, _yes_no(None if usable is None else bool(usable)),
                     f"{cfg.get('volume_usable_bars', '?')} of last {cfg.get('volume_usable_window', '?')} bars with volume "
                     "(E4 setting; superseded in the V1 spec, section 11.2)", "rule not frozen",
                     None if usable is None else bool(usable))
    else:
        w52 = _check("52-week (w52_complete)", E4, f"{NOT_RECORDED} ({e4_missing})", "bars >= high_window", "provisional")
        vol = _check("Volume usable", E4, f"{NOT_RECORDED} ({e4_missing})",
                     "E4 setting; superseded in the V1 spec, section 11.2", "rule not frozen")

    ca = bool(result["corporate_action_review_flag"])
    pb = bool(result["price_break_detected_flag"])
    ca_check = _check("Corporate-action review flag", SCANRUN, "FLAGGED" if ca else "not flagged",
                      "symbol has a non-RESOLVED review entry inside its fetched window (spec section 7)", "frozen", not ca)
    pb_check = _check("Price-break flag", SCANRUN, "FLAGGED" if pb else "not flagged",
                      f"close ratio < {PRICE_BREAK_LOW_RATIO} or > {PRICE_BREAK_HIGH_RATIO} (spec section 6; flag only)",
                      "frozen", not pb)
    checks = [sessions, ema, w52, vol, ca_check, pb_check]
    if failed:
        # flags were never evaluated for a FAILED symbol, so no row may carry a tick or cross
        for check in checks:
            check["ok"] = None
        for check in (ca_check, pb_check):
            check["result"] += " (acquisition failed: not evaluated)"
    return checks


def _e4_values(features: Optional[dict], quality: Optional[dict], e4: Optional[dict]) -> dict:
    cfg = e4["config"] if e4 else {}

    def label(key, fallback):
        period = cfg.get(key)
        return f"EMA{period}" if period else fallback

    def val(key):
        return features[key] if features and features.get(key) is not None else None

    usable = quality["volume_usable"] if quality else None
    rows = [
        ("Current price", val("close"), "close on the feature row's last date, from the E4 acquisition run"),
        (label("ema_medium", "EMA (medium)"), val("ema_medium"), None),
        (label("ema_long", "EMA (long)"), val("ema_long"), None),
        ("52W high", val("window_high"), "stored prior_high_long: highest high over the E4 high window"),
        ("52W low", None, "E4 does not store a 52-week low"),
        ("Volume ratio", val("relative_volume"), "stored relative_volume"),
        ("RSI", val("rsi"), "stored rsi"),
        ("ROC", val("roc"), "stored roc"),
        ("ATR %", val("atr_percent"), "stored atr_percent (ATR as a percentage); the E4 table has no absolute ATR column"),
        ("w52_complete", None if quality is None else bool(quality["w52_complete"]), None),
        ("Volume usable", None if usable is None else bool(usable), "E4 setting, rule not frozen"),
    ]
    return {
        "rows": [{"label": a, "value": b, "note": c} for a, b, c in rows],
        "last_date": features["last_date"] if features else None,
        "scan": None if e4 is None else {
            "scan_id": e4["scan_id"], "asof_date": e4["asof_date"], "provisional": True,
            "as_of_matches_run": e4["as_of_matches_run"], "run_latest_closed_session": e4["run_latest_closed_session"],
            "label": cfg.get("label"),
        },
        "quality_status": None if quality is None else {"status": quality["status"], "reason": quality["reason"]},
    }


def _provenance(conn, run: dict, symbol: str, result: dict, e4: Optional[dict]) -> dict:
    bars = _fetch_one_dict(
        conn,
        "SELECT COUNT(*) AS n, MIN(trading_date) AS first_date, MAX(trading_date) AS last_date, "
        "MAX(fetched_at_ist) AS retrieved_at, MIN(fetched_at_ist) AS first_retrieved_at "
        "FROM price_fetch_snapshots WHERE scan_run_id = ? AND symbol = ?",
        (run["run_id"], symbol),
    )
    adjustment = None
    if e4 is not None and queries._has_table(conn, "acquired_observations"):
        found = [r["adjustment_status"] for r in _fetch_all_dicts(
            conn,
            "SELECT DISTINCT adjustment_status FROM acquired_observations WHERE run_id = ? AND symbol = ?",
            (e4["acquisition_run_id"], symbol))]
        adjustment = "; ".join(found) if found else None

    # per-symbol check: recompute the canonical content hash of every stored bar of this
    # symbol in this run (bounded by that symbol's bar count) and compare to the stored hash.
    rows = _fetch_all_dicts(
        conn,
        "SELECT trading_date, open, high, low, close, volume, content_hash FROM price_fetch_snapshots "
        "WHERE scan_run_id = ? AND symbol = ? ORDER BY trading_date",
        (run["run_id"], symbol),
    )
    mismatched = [r["trading_date"] for r in rows if compute_content_hash_from_stored_row(r) != r["content_hash"]]
    return {
        "bars": bars,
        "adjustment": adjustment,
        "last_bar_hash": rows[-1]["content_hash"] if rows else None,
        "hash_check": {"label": "per-symbol check", "bars": len(rows), "mismatched": mismatched},
    }


def _status_history(conn, symbol: str) -> list[dict]:
    rows = _fetch_all_dicts(
        conn,
        """
        SELECT r.run_id, r.started_at, r.status AS run_status, r.symbols_filter_json, r.latest_closed_session,
               s.symbol_data_status, s.status_reason, s.available_session_count, s.missing_session_count
        FROM symbol_scan_results s JOIN scan_runs r ON r.run_id = s.scan_run_id
        WHERE s.symbol = ?
        ORDER BY r.started_at DESC
        LIMIT ?
        """,
        (symbol, STATUS_HISTORY_LIMIT),
    )
    for row in rows:
        filt = row.pop("symbols_filter_json")
        row["scan_label"] = f"SMOKE ({len(json.loads(filt))} symbols)" if filt else "FULL"
    return rows


def _flags(run: dict, result: dict, quality: Optional[dict], e4: Optional[dict], demo: bool) -> dict:
    cfg = e4["config"] if e4 else {}
    low = cfg.get("break_low_ratio", PRICE_BREAK_LOW_RATIO)
    high = cfg.get("break_high_ratio", PRICE_BREAK_HIGH_RATIO)
    has_break = bool(quality and quality.get("break_date"))
    price_break = {
        "flag": bool(result["price_break_detected_flag"]),
        "rule": f"close[t]/close[t-1] < {low} or > {high} (spec section 6, flag only; never truncates or excludes)",
        "rule_version": f"not recorded as a field; scan git commit {run.get('git_commit') or NOT_RECORDED}",
        "event_date": quality["break_date"] if has_break else None,
        "gap_ratio": quality["break_ratio"] if has_break else None,
        "detail_source": "E4 quality row (most recent break only)" if has_break else None,
    }

    review: dict = {
        "flag": bool(result["corporate_action_review_flag"]),
        "version": run.get("corporate_action_review_version"),
        "entries": [], "file_state": None, "message": None,
    }
    if demo:
        review["file_state"] = "not_read_demo"
        review["message"] = "review file is not read in demo mode (demo data is fabricated)"
        return {"price_break": price_break, "review": review}
    path = review_csv_path()
    try:
        loaded = corporate_actions.load_corporate_action_review(path)
    except corporate_actions.CorporateActionReviewCSVInvalidError as exc:
        review["file_state"] = "unavailable"
        review["message"] = f"review file unavailable: {exc}"
        return {"price_break": price_break, "review": review}
    if not loaded.entries:
        review["file_state"] = "empty"
        review["message"] = "review file empty: no symbols reviewed"
    else:
        review["file_state"] = "has_entries"
        review["entries"] = [e.__dict__ for e in loaded.entries if e.symbol == result["symbol"]]
        if not review["entries"]:
            review["message"] = f"{len(loaded.entries)} entries in the review file; none for this symbol"
    if run.get("corporate_action_review_version") and run["corporate_action_review_version"] != loaded.version:
        review["version_note"] = ("the review file on disk differs from the version this run used "
                                  "(it was edited after the run); entries below are the CURRENT file")
    return {"price_break": price_break, "review": review}


def build(conn, run: dict, symbol: str, result: dict, demo: bool) -> dict:
    e4 = queries.get_latest_e4_scan(conn)
    if e4 is not None:
        e4["run_latest_closed_session"] = run.get("latest_closed_session")
        e4["as_of_matches_run"] = bool(run.get("latest_closed_session")) and run["latest_closed_session"] == e4["asof_date"]
    features = quality = None
    if e4 is not None:
        features = queries.get_e4_features(conn, e4["scan_id"], [symbol], e4["acquisition_run_id"]).get(symbol)
        quality = aggregates.get_e4_quality_row(conn, e4, symbol)
    summary = queries.summarize_run(run)
    return {
        "demo": demo,
        "symbol": symbol,
        "result": result,
        "run": summary,
        "outdated": queries.is_outdated(run),
        "newer_run": get_newer_non_complete_run(conn, run),
        "checks": _status_checks(result, run, e4, quality, features),
        "e4": _e4_values(features, quality, e4),
        "provenance": _provenance(conn, run, symbol, result, e4),
        "ohlcv": queries.get_candles(conn, run["run_id"], symbol, limit=OHLCV_ROWS),
        "ohlcv_rows": OHLCV_ROWS,
        "history": _status_history(conn, symbol),
        "flags": _flags(run, result, quality, e4, demo),
        "required_sessions": REQUIRED_SESSIONS,
        "not_recorded": NOT_RECORDED,
    }

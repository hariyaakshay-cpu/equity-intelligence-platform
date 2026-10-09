"""Descriptive, read-only aggregates over the stored E4 scan.

Nothing here ranks, scores, bands or recommends: it counts and describes
what the scanner and the E4 indicator scan stored. Every share carries its
denominator, so a symbol lacking a value is visibly absent from `of` rather
than silently dropped. Like queries.py, this module only executes SELECTs on
a connection the caller opened read-only.
"""
from __future__ import annotations

import statistics
from typing import Optional

from dashboard.queries import (
    E4_FEATURE_COLUMNS,
    _fetch_all_dicts,
    _has_table,
    get_e4_status_counts,
    get_run,
)

_DIST_BUCKETS = ((0, 2), (2, 5), (5, 10), (10, 20), (20, None))


def _median(values: list) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 4) if values else None


def _share(count: int, of: int) -> dict:
    return {"count": count, "of": of, "pct": round(count / of * 100, 1) if of else None}


def get_e4_rows(conn, run_id: str, e4: dict) -> list[dict]:
    """One row per E4 feature set: indicators, sector, and the close on the
    feature set's last_date from the acquisition run (None if unavailable)."""
    has_obs = _has_table(conn, "acquired_observations")
    close_sql = "MAX(o.close)" if has_obs else "NULL"
    join = (
        "LEFT JOIN acquired_observations o ON o.run_id = ? AND o.symbol = f.symbol AND o.trading_date = f.last_date"
        if has_obs
        else ""
    )
    join_params = [e4["acquisition_run_id"]] if has_obs else []
    columns = ", ".join(f"f.{c}" for c in E4_FEATURE_COLUMNS)
    return _fetch_all_dicts(
        conn,
        f"""
        SELECT f.symbol, r.sector AS sector, {columns}, {close_sql} AS close
        FROM e4_feature_sets f
        LEFT JOIN symbol_scan_results r ON r.scan_run_id = ? AND r.symbol = f.symbol
        {join}
        WHERE f.scan_id = ?
        GROUP BY f.symbol
        """,
        [run_id, *join_params, e4["scan_id"]],
    )


def get_e4_breadth(rows: list[dict], e4: dict) -> dict:
    cfg = e4["config"]
    out: dict = {"symbols_with_features": len(rows)}

    above = {}
    for key, label in (("ema_short", "short"), ("ema_medium", "medium"), ("ema_long", "long")):
        usable = [r for r in rows if r[key] is not None and r["close"] is not None]
        above[label] = {"period": cfg.get(key), **_share(sum(1 for r in usable if r["close"] > r[key]), len(usable))}
    out["above_ema"] = above

    rsis = [r["rsi"] for r in rows if r["rsi"] is not None]
    hist = [0] * 10
    for v in rsis:
        hist[min(int(v // 10), 9)] += 1
    out["rsi"] = {
        "period": cfg.get("rsi_period"),
        "of": len(rsis),
        "median": _median(rsis),
        "histogram": [{"lo": i * 10, "hi": (i + 1) * 10, "count": n} for i, n in enumerate(hist)],
    }
    rocs = [r["roc"] for r in rows if r["roc"] is not None]
    out["roc"] = {
        "lookback": cfg.get("roc_lookback"),
        "median": _median(rocs),
        "positive": _share(sum(1 for v in rocs if v > 0), len(rocs)),
    }

    dists = [r["distance_from_high"] for r in rows if r["distance_from_high"] is not None]
    out["high_proximity"] = {
        "window": cfg.get("high_window"),
        "of": len(dists),
        "at_high": sum(1 for d in dists if d <= 0),
        "median_distance_pct": _median(dists),
        "buckets": [
            {"lo": lo, "hi": hi, "count": sum(1 for d in dists if d >= lo and (hi is None or d < hi))}
            for lo, hi in _DIST_BUCKETS
        ],
        "no_value": len(rows) - len(dists),
    }
    return out


def get_sector_strength(rows: list[dict]) -> list[dict]:
    """Per-sector descriptive statistics, alphabetical (no ordering by strength)."""
    by_sector: dict[str, list[dict]] = {}
    for row in rows:
        by_sector.setdefault(row["sector"] or "UNKNOWN", []).append(row)
    result = []
    for name in sorted(by_sector):
        members = by_sector[name]
        usable = [r for r in members if r["ema_medium"] is not None and r["close"] is not None]
        result.append(
            {
                "sector": name,
                "n": len(members),
                "above_ema_medium": _share(sum(1 for r in usable if r["close"] > r["ema_medium"]), len(usable)),
                "median_roc": _median([r["roc"] for r in members]),
                "median_relative_return": _median([r["relative_return"] for r in members]),
                "median_distance_from_high": _median([r["distance_from_high"] for r in members]),
            }
        )
    return result


SCANRUN_LAYER, E4_LAYER = "ScanRun", "E4"


def _break_ratio_text(q: dict) -> str:
    return f" (close ratio {q['break_ratio']:.4f})" if q.get("break_date") and q.get("break_ratio") is not None else ""


def _e4_warnings(q: dict, high_window, include_break: bool) -> list[dict]:
    """The warnings the E4 quality row `q` records, each tagged layer "E4". The break warning is added only when
    `include_break`: for a symbol whose ScanRun price-break flag is set, the E4 break is reported as a part of
    that warning instead (see get_data_quality)."""
    out = []
    if q["status"] != "VALID":
        out.append({"code": "e4_" + q["status"], "layer": E4_LAYER, "message": q["reason"] or "no reason recorded by the E4 scan"})
    if not q["w52_complete"]:
        out.append({"code": "e4_no_full_high_window", "layer": E4_LAYER,
                    "message": f"fewer than {high_window or 'the required'} bars: the high-window distance is unavailable"})
    if not q["volume_usable"]:
        out.append({"code": "e4_volume_unusable", "layer": E4_LAYER, "message": "volume history not usable: relative volume unavailable"})
    if include_break and q.get("break_date"):
        out.append({"code": "e4_break", "layer": E4_LAYER,
                    "message": f"E4 detected a break on {q['break_date']}{_break_ratio_text(q)}; indicators use later bars only"})
    return out


def _layer_summary(symbol_warnings: dict[str, list[str]], total: int) -> dict:
    """{"symbols_total", "symbols_with_warnings", "symbols_without_warning", "warning_counts"} for ONE layer:
    `symbol_warnings` maps each symbol with at least one warning in that layer to its warning codes."""
    counts: dict[str, int] = {}
    for codes in symbol_warnings.values():
        for code in codes:
            counts[code] = counts.get(code, 0) + 1
    return {"symbols_total": total, "symbols_with_warnings": len(symbol_warnings),
            "symbols_without_warning": total - len(symbol_warnings), "warning_counts": counts}


def get_data_quality(conn, run_id: str, e4: Optional[dict], symbol: Optional[str] = None) -> dict:
    """Every symbol with at least one warning, each warning with its reason.
    Nothing is dropped: a symbol is listed whenever the scan or the E4 scan
    recorded anything about it.

    `symbols_*`, `warning_counts` and `issues` keep their meaning: they mix the two layers (a symbol counts as
    "with a warning" when either layer recorded something). Each warning also carries `layer` ("ScanRun" or
    "E4"), and `layers` counts each layer on its own, never added together:
    `layers["scanrun"]` over the scan run's symbols, `layers["e4"]` over ALL of the E4 scan's quality rows
    (None when there is no COMPLETE E4 scan), with `not_listed_with_warnings` = E4 symbols with a warning that
    are not among the scan run's symbols (so absent from `issues`). The price-break warning of a symbol that
    also has an E4 break keeps its full `message` and adds `parts`, one entry per layer."""
    where, params = "scan_run_id = ?", [run_id]
    if symbol:
        where += " AND symbol = ?"
        params.append(symbol)
    results = _fetch_all_dicts(conn, f"SELECT * FROM symbol_scan_results WHERE {where}", params)
    run = get_run(conn, run_id) or {}
    review_version = run.get("corporate_action_review_version")

    e4_quality: dict[str, dict] = {}
    if e4 is not None and _has_table(conn, "e4_data_quality_results"):
        qwhere, qparams = "scan_id = ?", [e4["scan_id"]]
        if symbol:
            qwhere += " AND symbol = ?"
            qparams.append(symbol)
        for row in _fetch_all_dicts(conn, f"SELECT * FROM e4_data_quality_results WHERE {qwhere}", qparams):
            e4_quality[row["symbol"]] = row
    high_window = e4["config"].get("high_window") if e4 else None

    issues = []
    for r in results:
        warnings = []
        if r["symbol_data_status"] != "VALID":
            warnings.append({"code": r["symbol_data_status"], "layer": SCANRUN_LAYER,
                             "message": r["status_reason"] or "no reason recorded by the scanner"})
        if r["history_gaps_flag"]:
            warnings.append({
                "code": "history_gaps", "layer": SCANRUN_LAYER,
                "message": f"{r['missing_session_count']} missing session(s); {r['available_session_count']} available",
            })
        if r["corporate_action_review_flag"]:
            warnings.append({"code": "corporate_action_review", "layer": SCANRUN_LAYER,
                             "message": f"listed in the corporate-action review file (version {review_version or 'unknown'})"})
        q = e4_quality.get(r["symbol"])
        has_break = bool(q and q.get("break_date"))
        if r["price_break_detected_flag"]:
            base = "close-to-close jump consistent with an unadjusted split/bonus"
            warning = {"code": "price_break_detected", "layer": SCANRUN_LAYER, "message": base}
            if has_break:
                break_text = f"break on {q['break_date']}{_break_ratio_text(q)}"
                warning["message"] = f"{base}; E4 {break_text}"      # unchanged text for existing readers
                warning["parts"] = [{"layer": SCANRUN_LAYER, "text": base}, {"layer": E4_LAYER, "code": "e4_break", "text": break_text}]
            warnings.append(warning)
        if r["non_eq_series_flag"]:
            warnings.append({"code": "non_eq_series", "layer": SCANRUN_LAYER, "message": f"series {r['series'] or 'unknown'} is not EQ"})
        if q:
            warnings.extend(_e4_warnings(q, high_window, include_break=not r["price_break_detected_flag"]))
        if warnings:
            issues.append({
                "symbol": r["symbol"], "company_name": r["company_name"], "sector": r["sector"],
                "status": r["symbol_data_status"], "warnings": warnings,
            })

    counts: dict[str, int] = {}
    for issue in issues:
        for w in issue["warnings"]:
            counts[w["code"]] = counts.get(w["code"], 0) + 1
    scanrun_codes = {i["symbol"]: [w["code"] for w in i["warnings"] if w["layer"] == SCANRUN_LAYER] for i in issues}
    scanrun_layer = _layer_summary({s: c for s, c in scanrun_codes.items() if c}, len(results))
    e4_layer = None
    if e4 is not None:
        e4_codes = {s: [w["code"] for w in _e4_warnings(q, high_window, include_break=True)] for s, q in e4_quality.items()}
        e4_codes = {s: c for s, c in e4_codes.items() if c}
        counted = get_e4_status_counts(conn, e4["scan_id"]) if not symbol else None
        scanrun_symbols = {r["symbol"] for r in results}
        e4_layer = {
            "scan_id": e4["scan_id"],
            **_layer_summary(e4_codes, counted["total"] if counted else len(e4_quality)),
            "not_listed_with_warnings": len([s for s in e4_codes if s not in scanrun_symbols]),
        }
    return {
        "symbols_total": len(results),
        "symbols_with_warnings": len(issues),
        "symbols_without_warning": len(results) - len(issues),
        "warning_counts": counts,
        "issues": issues,
        "layers": {"scanrun": scanrun_layer, "e4": e4_layer},
    }


def get_chart_bars(conn, e4: dict, symbol: str, limit: int = 400) -> list[dict]:
    """Daily bars from the E4 scan's acquisition run, oldest first."""
    if not _has_table(conn, "acquired_observations"):
        return []
    rows = _fetch_all_dicts(
        conn,
        """
        SELECT trading_date, MAX(open) AS open, MAX(high) AS high, MAX(low) AS low,
               MAX(close) AS close, MAX(volume) AS volume
        FROM acquired_observations
        WHERE run_id = ? AND symbol = ?
        GROUP BY trading_date
        ORDER BY trading_date DESC
        LIMIT ?
        """,
        (e4["acquisition_run_id"], symbol, limit),
    )
    return list(reversed(rows))


def get_history_depth(conn, e4: dict) -> Optional[dict]:
    """How much stored history the E4 acquisition run holds -- measured, so the
    Research tab never states a stale depth."""
    if not _has_table(conn, "acquired_observations"):
        return None
    rows = _fetch_all_dicts(
        conn,
        "SELECT MIN(trading_date) AS first_date, MAX(trading_date) AS last_date, "
        "COUNT(DISTINCT trading_date) AS sessions, COUNT(DISTINCT symbol) AS symbols "
        "FROM acquired_observations WHERE run_id = ?",
        (e4["acquisition_run_id"],),
    )
    depth = rows[0] if rows and rows[0]["sessions"] else None
    if depth is None:
        return None
    if _has_table(conn, "acquired_benchmark"):
        depth["benchmark_sessions"] = conn.execute(
            "SELECT COUNT(DISTINCT trading_date) FROM acquired_benchmark WHERE run_id = ?",
            (e4["acquisition_run_id"],),
        ).fetchone()[0]
    return depth


def get_e4_quality_row(conn, e4: dict, symbol: str) -> Optional[dict]:
    if not _has_table(conn, "e4_data_quality_results"):
        return None
    rows = _fetch_all_dicts(
        conn, "SELECT * FROM e4_data_quality_results WHERE scan_id = ? AND symbol = ?", (e4["scan_id"], symbol)
    )
    return rows[0] if rows else None

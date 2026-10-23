"""E4 runner: read a COMPLETE, full-universe E1-E3 run, detect breaks,
compute raw features, persist under an e4_scan_runs row.

Reads stored observations only (no vendor calls). e4_scan_runs.status is
RUNNING -> COMPLETE | FAILED; COMPLETE is set in the final transaction and
only when every universe member has an e4_data_quality_results row.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from equity_intel.contracts.quality import DataStatus
from equity_intel.features.adjustment_basis import ist_date, post_fetch_events, stale_basis_reason
from equity_intel.features.compute import compute_instrument
from equity_intel.features.config import IndicatorConfig
from equity_intel.persistence.connection import connect
from equity_intel.scanner.corporate_actions import load_corporate_action_review
from equity_intel.scanner.execution_guard import assert_no_forbidden_modules_loaded


DEFAULT_REVIEW_CSV = Path(__file__).resolve().parents[2] / "data" / "reference" / "corporate_action_review.csv"


def _is_full_run(report: dict, cfg: IndicatorConfig) -> bool:
    return (report.get("universe_count", 0) >= cfg.minimum_universe_count
            and report.get("requested_count") == report.get("mapped_count")
            and report.get("benchmark_status") == "OK")


def _select_acquisition_run(connection, cfg: IndicatorConfig, requested: str | None) -> tuple[str, dict]:
    if requested is not None:
        row = connection.execute("SELECT run_id,status,report_json FROM acquisition_runs WHERE run_id=?", (requested,)).fetchone()
        if row is None or row["status"] != "COMPLETE":
            raise RuntimeError(f"Acquisition run {requested} is not COMPLETE")
        report = json.loads(row["report_json"])
        if report.get("benchmark_status") != "OK":
            raise RuntimeError(f"Acquisition run {requested} has no benchmark; re-run scripts/equity_data_acquisition.py")
        return row["run_id"], report
    for row in connection.execute(
            "SELECT run_id,report_json FROM acquisition_runs WHERE status='COMPLETE' ORDER BY run_started_at DESC"):
        report = json.loads(row["report_json"])
        if _is_full_run(report, cfg):
            return row["run_id"], report
    raise RuntimeError(
        f"No COMPLETE full-universe acquisition run with a benchmark found (universe_count >= {cfg.minimum_universe_count}, "
        "every mapped symbol requested, benchmark OK); run scripts/equity_data_acquisition.py first")


def run_feature_scan(cfg: IndicatorConfig, *, db_path: str | Path | None = None,
                     acquisition_run_id: str | None = None,
                     corporate_action_review_path: str | Path = DEFAULT_REVIEW_CSV,
                     now: datetime | None = None) -> dict:
    assert_no_forbidden_modules_loaded()
    review = load_corporate_action_review(corporate_action_review_path)  # missing/malformed aborts, as in Section 7
    now = now or datetime.now(timezone.utc)
    connection = connect() if db_path is None else connect(db_path)
    scan_id = f"scan-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    try:
        acquisition_run_id, report = _select_acquisition_run(connection, cfg, acquisition_run_id)
        connection.execute(
            "INSERT INTO e4_scan_runs(scan_id,acquisition_run_id,started_at,status,calendar_status,constituents_sha256,"
            "instrument_master_sha256,indicator_config_json,corporate_action_review_sha256) VALUES(?,?,?,?,?,?,?,?,?)",
            (scan_id, acquisition_run_id, now.isoformat(), "RUNNING", report["calendar_status"],
             report["constituents_sha256"], report["instrument_master_sha256"], json.dumps(cfg.as_dict(), sort_keys=True),
             review.version))
        fetch_date = ist_date(connection.execute("SELECT run_started_at FROM acquisition_runs WHERE run_id=?",
                                                 (acquisition_run_id,)).fetchone()[0])
        connection.commit()
    except Exception:
        connection.close()
        raise

    try:
        universe = [r["symbol"] for r in connection.execute(
            "SELECT symbol FROM instrument_mappings WHERE run_id=? AND mapping_status='MAPPED' ORDER BY symbol", (acquisition_run_id,))]
        acquisition_status = {r["symbol"]: (r["status"], r["reason"]) for r in connection.execute(
            "SELECT symbol,status,reason FROM symbol_acquisition_results WHERE run_id=?", (acquisition_run_id,))}
        benchmark = {r["trading_date"]: r["close"] for r in connection.execute(
            "SELECT trading_date,close FROM acquired_benchmark WHERE run_id=?", (acquisition_run_id,))}
        if not benchmark:
            raise RuntimeError(f"Acquisition run {acquisition_run_id} has no stored benchmark observations")
        results = []  # (symbol, status, reason, features|None, detail|None, last_date|None, break_date|None)
        for symbol in universe:
            rows = connection.execute(
                "SELECT trading_date,high,low,close,volume FROM acquired_observations WHERE run_id=? AND symbol=? ORDER BY trading_date",
                (acquisition_run_id, symbol)).fetchall()
            if not rows:
                acq_status, acq_reason = acquisition_status.get(symbol, ("MISSING", None))
                status = DataStatus.INSUFFICIENT_HISTORY if acq_status == "INSUFFICIENT_HISTORY" else DataStatus.FAILED
                reason = f"acquisition {acq_status}: {acq_reason}" if acq_reason else f"acquisition {acq_status}"
                results.append((symbol, status, reason, None, None, None, None))
                continue
            dates = [r["trading_date"] for r in rows]
            quality, features, detail = compute_instrument(
                symbol, [r["high"] for r in rows], [r["low"] for r in rows], [r["close"] for r in rows],
                [r["volume"] for r in rows], cfg, dates=dates, benchmark=benchmark)
            break_date = dates[detail["break_date_index"]] if detail["break_date_index"] is not None else None
            results.append((symbol, quality.status, quality.reason, features, detail, dates[-1], break_date))

        asof = max((r[5] for r in results if r[5]), default=None)
        counts: dict[str, int] = {}
        flagged = 0
        stale_basis: list[str] = []
        scan_date = ist_date(now)
        with connection:
            for symbol, status, reason, f, detail, last_date, break_date in results:
                # Stale: last observation older than the newest date in the run. A symbol that
                # failed validation or lacks history keeps that (more severe) status.
                if f is not None and status is DataStatus.VALID and last_date < asof:
                    status = DataStatus.STALE
                    reason = f"last observation {last_date}, run as-of {asof}"
                # Series fetched on/before a later corporate action are on the pre-event basis: withhold features.
                basis_reason = stale_basis_reason(post_fetch_events(review, symbol, fetch_date, scan_date),
                                                  acquisition_run_id, fetch_date)
                withhold = basis_reason is not None and f is not None and status is not DataStatus.FAILED
                if withhold:
                    status, reason = DataStatus.STALE, basis_reason
                    stale_basis.append(symbol)
                counts[status.value] = counts.get(status.value, 0) + 1
                flagged += break_date is not None
                connection.execute(
                    "INSERT INTO e4_data_quality_results VALUES(?,?,?,?,?,?,?,?,?)",
                    (scan_id, symbol, status.value, reason, f.n_bars if f else 0, int(bool(f and f.w52_complete)),
                     break_date, detail.get("break_ratio") if detail else None,
                     int(detail["volume_usable"]) if detail else None))
                if f is not None and status is not DataStatus.FAILED and not withhold:
                    connection.execute(
                        "INSERT INTO e4_feature_sets(scan_id,symbol,last_date,ema_short,ema_medium,ema_long,rsi,roc,relative_return,"
                        "relative_volume,distance_from_high,prior_high_long,atr_percent) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (scan_id, symbol, last_date, f.ema_short, f.ema_medium, f.ema_long, f.rsi, f.roc,
                         f.relative_return, f.relative_volume, f.distance_from_high, f.prior_high_long, f.atr_percent))
            covered = connection.execute("SELECT COUNT(*) FROM e4_data_quality_results WHERE scan_id=?", (scan_id,)).fetchone()[0]
            if covered != len(universe):
                raise RuntimeError(f"data_quality_results covers {covered} of {len(universe)} universe members")
            connection.execute("UPDATE e4_scan_runs SET status='COMPLETE',completed_at=?,asof_date=? WHERE scan_id=?",
                               (datetime.now(timezone.utc).isoformat(), asof, scan_id))
        return {"scan_id": scan_id, "status": "COMPLETE", "acquisition_run_id": acquisition_run_id,
                "universe": len(universe), "asof_date": asof, "flagged_breaks": flagged, "quality": counts,
                "stale_adjustment_basis": stale_basis}
    except Exception as error:
        with connection:
            connection.execute("UPDATE e4_scan_runs SET status='FAILED',completed_at=?,failure_reason=? WHERE scan_id=?",
                               (datetime.now(timezone.utc).isoformat(), f"{type(error).__name__}: {error}", scan_id))
        raise
    finally:
        connection.close()

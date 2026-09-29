"""E4 runner: read the latest COMPLETE E1-E3 run, detect breaks, compute
raw features, persist under a scan_runs row.

Reads stored observations only (no vendor calls). scan_runs.status is
RUNNING -> COMPLETE | FAILED; COMPLETE is set in the final transaction and
only when every universe member has a data_quality_results row.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from equity_intel.features.compute import compute_instrument
from equity_intel.features.config import IndicatorConfig
from equity_intel.persistence.connection import connect
from equity_intel.scanner.execution_guard import assert_no_forbidden_modules_loaded


def run_feature_scan(cfg: IndicatorConfig, *, db_path: str | Path | None = None,
                     acquisition_run_id: str | None = None) -> dict:
    assert_no_forbidden_modules_loaded()
    connection = connect() if db_path is None else connect(db_path)
    scan_id = f"scan-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    started = datetime.now(timezone.utc).isoformat()
    try:
        if acquisition_run_id is None:
            row = connection.execute(
                "SELECT run_id FROM acquisition_runs WHERE status='COMPLETE' ORDER BY run_started_at DESC LIMIT 1").fetchone()
            if row is None:
                raise RuntimeError("No COMPLETE acquisition run found; run scripts/equity_data_acquisition.py first")
            acquisition_run_id = row["run_id"]
        run = connection.execute("SELECT status, report_json FROM acquisition_runs WHERE run_id=?", (acquisition_run_id,)).fetchone()
        if run is None or run["status"] != "COMPLETE":
            raise RuntimeError(f"Acquisition run {acquisition_run_id} is not COMPLETE")
        report = json.loads(run["report_json"])
        connection.execute(
            "INSERT INTO scan_runs(scan_id,acquisition_run_id,started_at,status,calendar_status,constituents_sha256,"
            "instrument_master_sha256,indicator_config_json) VALUES(?,?,?,?,?,?,?,?)",
            (scan_id, acquisition_run_id, started, "RUNNING", report["calendar_status"], report["constituents_sha256"],
             report["instrument_master_sha256"], json.dumps(cfg.as_dict(), sort_keys=True)))
        connection.commit()
    except Exception:
        connection.close()
        raise

    try:
        universe = [r["symbol"] for r in connection.execute(
            "SELECT symbol FROM instrument_mappings WHERE run_id=? AND mapping_status='MAPPED' ORDER BY symbol", (acquisition_run_id,))]
        acquisition_status = {r["symbol"]: (r["status"], r["reason"]) for r in connection.execute(
            "SELECT symbol,status,reason FROM symbol_acquisition_results WHERE run_id=?", (acquisition_run_id,))}
        counts: dict[str, int] = {}
        flagged = 0
        asof = None
        with connection:
            for symbol in universe:
                rows = connection.execute(
                    "SELECT trading_date,high,low,close,volume FROM acquired_observations WHERE run_id=? AND symbol=? ORDER BY trading_date",
                    (acquisition_run_id, symbol)).fetchall()
                if not rows:
                    status, reason = acquisition_status.get(symbol, ("MISSING", None))
                    connection.execute(
                        "INSERT INTO data_quality_results(scan_id,symbol,status,reason,n_bars) VALUES(?,?,?,?,0)",
                        (scan_id, symbol, "INSUFFICIENT_HISTORY" if status == "INSUFFICIENT_HISTORY" else "FAILED",
                         f"acquisition {status}: {reason}" if reason else f"acquisition {status}"))
                    counts["INSUFFICIENT_HISTORY" if status == "INSUFFICIENT_HISTORY" else "FAILED"] = counts.get(
                        "INSUFFICIENT_HISTORY" if status == "INSUFFICIENT_HISTORY" else "FAILED", 0) + 1
                    continue
                dates = [r["trading_date"] for r in rows]
                quality, f, detail = compute_instrument(
                    symbol, [r["high"] for r in rows], [r["low"] for r in rows], [r["close"] for r in rows],
                    [r["volume"] for r in rows], cfg)
                break_date = dates[detail["break_date_index"]] if detail["break_date_index"] is not None else None
                flagged += break_date is not None
                asof = max(asof, dates[-1]) if asof else dates[-1]
                counts[quality.status.value] = counts.get(quality.status.value, 0) + 1
                connection.execute(
                    "INSERT INTO data_quality_results VALUES(?,?,?,?,?,?,?,?,?)",
                    (scan_id, symbol, quality.status.value, quality.reason, f.n_bars, int(bool(f.w52_complete)),
                     break_date, detail["break_ratio"], int(detail["volume_usable"])))
                connection.execute(
                    "INSERT INTO feature_sets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (scan_id, symbol, dates[-1], f.ema_short, f.ema_medium, f.ema_long, f.rsi, f.roc,
                     f.relative_volume, f.distance_from_high, f.prior_high_long, f.atr_percent))
            covered = connection.execute("SELECT COUNT(*) FROM data_quality_results WHERE scan_id=?", (scan_id,)).fetchone()[0]
            if covered != len(universe):
                raise RuntimeError(f"data_quality_results covers {covered} of {len(universe)} universe members")
            connection.execute("UPDATE scan_runs SET status='COMPLETE',completed_at=?,asof_date=? WHERE scan_id=?",
                               (datetime.now(timezone.utc).isoformat(), asof, scan_id))
        return {"scan_id": scan_id, "status": "COMPLETE", "acquisition_run_id": acquisition_run_id,
                "universe": len(universe), "asof_date": asof, "flagged_breaks": flagged, "quality": counts}
    except Exception as error:
        with connection:
            connection.execute("UPDATE scan_runs SET status='FAILED',completed_at=?,failure_reason=? WHERE scan_id=?",
                               (datetime.now(timezone.utc).isoformat(), f"{type(error).__name__}: {error}", scan_id))
        raise
    finally:
        connection.close()

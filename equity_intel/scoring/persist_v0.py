"""PROVISIONAL v0: score one stored E4 scan and persist the result.

Reads e4_feature_sets / e4_data_quality_results of ONE COMPLETE e4 scan and
writes e4_provisional_scores (idempotent per scan_id). No vendor calls, no
broker or engine imports. This module never opens a database itself: the
caller passes a connection from equity_intel.persistence.connection.

Every row carries LABEL = "PROVISIONAL - not B2-authoritative". Candidates
and ranks are descriptive model output, not trade advice or expectancy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from equity_intel.contracts.features import FeatureSet
from equity_intel.scoring import components_v0
from equity_intel.scoring import provisional_v0 as cfg

DDL = """
CREATE TABLE IF NOT EXISTS e4_provisional_scores (
 scan_id TEXT NOT NULL, symbol TEXT NOT NULL, asof_date TEXT, calendar_status TEXT,
 trend INTEGER, momentum INTEGER, relative_strength INTEGER, volume INTEGER, structure INTEGER,
 composite INTEGER, candidate INTEGER NOT NULL, rank INTEGER, exclusion TEXT,
 candidate_cutoff INTEGER NOT NULL, watchlist_limit INTEGER NOT NULL,
 label TEXT NOT NULL, scored_at TEXT NOT NULL,
 PRIMARY KEY (scan_id, symbol)
);
"""

HORIZON_DDL = """
CREATE TABLE IF NOT EXISTS e4_provisional_horizons (
 scan_id TEXT NOT NULL, symbol TEXT NOT NULL, horizon TEXT NOT NULL, score INTEGER,
 candidate INTEGER NOT NULL, rank INTEGER, exclusion TEXT,
 cutoff_pct INTEGER NOT NULL, watchlist_limit INTEGER NOT NULL, label TEXT NOT NULL, scored_at TEXT NOT NULL,
 PRIMARY KEY (scan_id, symbol, horizon)
);
"""

FEATURE_COLUMNS = (
    "ema_short", "ema_medium", "ema_long", "ema_medium_lag", "rsi", "roc", "relative_return",
    "relative_volume", "distance_from_high", "prior_high_short", "prior_high_medium",
    "prior_high_long", "atr_percent", "close",
)


def ensure_table(conn) -> None:
    conn.executescript(DDL)
    conn.executescript(HORIZON_DDL)


def latest_complete_scan(conn) -> Optional[dict]:
    row = conn.execute(
        "SELECT scan_id, asof_date, calendar_status FROM e4_scan_runs "
        "WHERE status='COMPLETE' ORDER BY started_at DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _features(row) -> FeatureSet:
    values = {c: row[c] for c in FEATURE_COLUMNS}
    return FeatureSet(instrument_id=row["symbol"], n_bars=row["n_bars"],
                      w52_complete=None if row["w52_complete"] is None else bool(row["w52_complete"]), **values)


def score_scan(conn, scan_id: str, *, candidate_cutoff: int = cfg.CANDIDATE_CUTOFF,
               watchlist_limit: int = cfg.WATCHLIST_LIMIT, horizon_cutoff_pct: int = cfg.HORIZON_CUTOFF_PCT,
               horizon_watchlist_limit: int = cfg.HORIZON_WATCHLIST_LIMIT, now: Optional[datetime] = None) -> dict:
    ensure_table(conn)
    run = conn.execute("SELECT scan_id, asof_date, calendar_status, status FROM e4_scan_runs WHERE scan_id=?",
                       (scan_id,)).fetchone()
    if run is None or run["status"] != "COMPLETE":
        raise RuntimeError(f"e4 scan {scan_id!r} is not a COMPLETE scan")
    cols = ", ".join(f"f.{c}" for c in FEATURE_COLUMNS)
    rows = conn.execute(
        f"SELECT f.symbol, {cols}, q.status AS q_status, q.n_bars, q.w52_complete, q.break_date "
        "FROM e4_feature_sets f JOIN e4_data_quality_results q ON q.scan_id=f.scan_id AND q.symbol=f.symbol "
        "WHERE f.scan_id=?", (scan_id,)).fetchall()
    scored = []
    horizon_rows = []
    for r in rows:
        result = components_v0.score_instrument(_features(r))
        by_name = {c.component_name: c.score for c in result.components}
        if r["q_status"] != "VALID":
            exclusion = f"DATA_STATUS_{r['q_status']}"
        elif r["break_date"] is not None:
            exclusion = "CORPORATE_ACTION_BREAK_FLAG"
        elif result.composite is None:
            exclusion = "COMPOSITE_NONE"
        else:
            exclusion = None
        is_candidate = exclusion is None and result.composite >= candidate_cutoff
        scored.append([r["symbol"], by_name, result.composite, is_candidate, exclusion])
        horizon_rows.append((r["symbol"], exclusion, components_v0.horizon_scores(_features(r))))
    ranked = sorted((s for s in scored if s[3]), key=lambda s: (-s[2], s[0]))
    rank_of = {s[0]: i + 1 for i, s in enumerate(ranked)}
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    conn.execute("DELETE FROM e4_provisional_scores WHERE scan_id=?", (scan_id,))
    for symbol, by_name, composite, is_candidate, exclusion in scored:
        conn.execute(
            "INSERT INTO e4_provisional_scores VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (scan_id, symbol, run["asof_date"], run["calendar_status"], by_name["trend"], by_name["momentum"],
             by_name["relative_strength"], by_name["volume"], by_name["structure"], composite,
             int(is_candidate), rank_of.get(symbol), exclusion, candidate_cutoff, watchlist_limit,
             cfg.LABEL, stamp))
    conn.execute("DELETE FROM e4_provisional_horizons WHERE scan_id=?", (scan_id,))
    horizon_summary = {}
    for horizon in ("short", "medium"):
        entries = []
        for symbol, base_exclusion, scores in horizon_rows:
            score = scores[horizon]
            exclusion = base_exclusion or (None if score is not None else "HORIZON_SCORE_NONE")
            entries.append([symbol, score, exclusion, exclusion is None and score >= horizon_cutoff_pct])
        ranked_h = sorted((e for e in entries if e[3]), key=lambda e: (-e[1], e[0]))
        rank_h = {e[0]: i + 1 for i, e in enumerate(ranked_h)}
        for symbol, score, exclusion, is_cand in entries:
            conn.execute("INSERT INTO e4_provisional_horizons VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (scan_id, symbol, horizon, score, int(is_cand), rank_h.get(symbol), exclusion,
                          horizon_cutoff_pct, horizon_watchlist_limit, cfg.LABEL, stamp))
        horizon_summary[horizon] = {"candidates": len(ranked_h), "watchlist": min(len(ranked_h), horizon_watchlist_limit)}
    conn.commit()
    return {"scan_id": scan_id, "horizons": horizon_summary, "asof_date": run["asof_date"], "scored": len(scored),
            "with_composite": sum(1 for s in scored if s[2] is not None),
            "candidates": len(ranked), "watchlist": min(len(ranked), watchlist_limit), "label": cfg.LABEL}

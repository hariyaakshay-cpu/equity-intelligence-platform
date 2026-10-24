"""PROVISIONAL v0 daily signals view (read-only).

Reads e4_provisional_scores (written by scripts/equity_score_v0.py) for the
latest COMPLETE E4 scan that has scores. Descriptive model output only: every
row is labelled PROVISIONAL - not B2-authoritative, and nothing here is trade
advice or a claim of expectancy. Never writes; never imports sqlite3.
"""
from __future__ import annotations

from typing import Optional

from dashboard import queries

BANNER = "PROVISIONAL scoring v0 - not B2-authoritative - research only - not trade advice"

NOTICE = ("PROVISIONAL scoring v0 - not B2-authoritative. Scores come from proposed bands, the candidate "
          "cutoff and watchlist size are placeholders, and no expectancy has been tested (Stage 4). "
          "This is a daily, end-of-day view; it is not trade advice.")


def _rows(conn, sql, params=()) -> list[dict]:
    return queries._fetch_all_dicts(conn, sql, list(params))


def build(conn, limit: Optional[int] = None) -> dict:
    if not queries._has_table(conn, "e4_provisional_scores"):
        return {"available": False, "notice": NOTICE,
                "message": "No provisional scores yet. Run scripts/equity_e4_scan.py, then scripts/equity_score_v0.py."}
    head = _rows(conn,
        "SELECT s.scan_id, s.asof_date, s.calendar_status, s.candidate_cutoff, s.watchlist_limit, s.label, s.scored_at "
        "FROM e4_provisional_scores s JOIN e4_scan_runs r ON r.scan_id = s.scan_id AND r.status = 'COMPLETE' "
        "ORDER BY r.started_at DESC, s.scored_at DESC LIMIT 1")
    if not head:
        return {"available": False, "notice": NOTICE, "message": "No scored COMPLETE E4 scan yet."}
    meta = head[0]
    scan_id = meta["scan_id"]
    counts = _rows(conn,
        "SELECT COUNT(*) AS scored, SUM(composite IS NOT NULL) AS with_composite, SUM(candidate) AS candidates "
        "FROM e4_provisional_scores WHERE scan_id = ?", (scan_id,))[0]
    exclusions = _rows(conn,
        "SELECT exclusion, COUNT(*) AS n FROM e4_provisional_scores WHERE scan_id = ? AND exclusion IS NOT NULL "
        "GROUP BY exclusion ORDER BY n DESC", (scan_id,))
    cap = "" if limit is None else f" LIMIT {int(limit)}"
    candidates = _rows(conn,
        "SELECT s.rank, s.symbol, s.composite, s.trend, s.momentum, s.relative_strength, s.volume, s.structure, "
        "f.close, f.rsi, f.relative_volume, f.distance_from_high "
        "FROM e4_provisional_scores s LEFT JOIN e4_feature_sets f ON f.scan_id = s.scan_id AND f.symbol = s.symbol "
        "WHERE s.scan_id = ? AND s.candidate = 1 ORDER BY s.rank" + cap, (scan_id,))
    for row in candidates:
        row["watchlist"] = row["rank"] is not None and row["rank"] <= meta["watchlist_limit"]
    horizons = {}
    for horizon in ("short", "medium"):
        if not queries._has_table(conn, "e4_provisional_horizons"):
            horizons[horizon] = []
            continue
        horizon_rows = _rows(conn,
            "SELECT h.rank, h.symbol, h.score, h.watchlist_limit, f.close, f.rsi, f.relative_volume, f.distance_from_high "
            "FROM e4_provisional_horizons h LEFT JOIN e4_feature_sets f ON f.scan_id = h.scan_id AND f.symbol = h.symbol "
            "WHERE h.scan_id = ? AND h.horizon = ? AND h.candidate = 1 ORDER BY h.rank" + cap, (scan_id, horizon))
        for row in horizon_rows:
            row["watchlist"] = row["rank"] <= row["watchlist_limit"]
        horizons[horizon] = horizon_rows
    expected = queries.expected_latest_session()
    outdated = meta["asof_date"] is not None and meta["asof_date"] < expected.isoformat()
    return {"available": True, "notice": NOTICE, "meta": meta, "counts": counts, "exclusions": exclusions,
            "candidates": candidates, "horizons": horizons, "expected_latest_session": expected.isoformat(), "outdated": outdated,
            "intraday_note": "Intraday signals are not built yet; this page shows daily signals only."}

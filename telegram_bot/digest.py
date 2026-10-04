"""Build the daily scanner digest text from the read-only equity_intel DB.

Every function takes an already-open read-only sqlite3 connection. Nothing
here writes, and nothing here ranks symbols as buy/sell.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from dashboard import queries

DISCLAIMER = "Research data only. Not a trade recommendation. No signals, no scores."
TELEGRAM_MAX_CHARS = 4096
NEAR_HIGH_COUNT = 5


def _pct(part: int, whole: int) -> str:
    return f"{part} of {whole} ({100 * part / whole:.1f}%)" if whole else "n/a"


def _breadth(features: dict[str, dict]) -> list[str]:
    lines = []
    for label, column in (("EMA 200", "ema_long"), ("EMA 50", "ema_medium"), ("EMA 20", "ema_short")):
        comparable = [f for f in features.values() if f.get("close") is not None and f.get(column) is not None]
        above = sum(1 for f in comparable if f["close"] > f[column])
        lines.append(f"  Above {label}: {_pct(above, len(comparable))}")
    roc = [f["roc"] for f in features.values() if f.get("roc") is not None]
    lines.append(f"  Positive ROC: {_pct(sum(1 for r in roc if r > 0), len(roc))}")
    return lines


def build_digest(conn, now: Optional[datetime] = None) -> str:
    run = queries.get_latest_complete_run(conn)
    if run is None:
        return f"Equity scanner digest\nNo completed scan run found.\n\n{DISCLAIMER}"

    summary = queries.summarize_run(run)
    session = summary.get("latest_closed_session") or "unknown"
    lines = [f"Equity scanner digest - latest closed session {session}"]
    if queries.is_outdated(run, now):
        lines.append("Data may be outdated (approximate: market holidays not known).")

    e4 = queries.get_latest_e4_scan(conn)
    if e4 is None:
        lines.append("No completed indicator (E4) scan; breadth unavailable.")
    else:
        total, rows = queries.get_candidates(
            conn, run["run_id"], page=1, page_size=1000,
            sort="distance_from_high", sort_dir="asc", e4_scan_id=e4["scan_id"],
        )
        features = queries.get_e4_features(
            conn, e4["scan_id"], [r["symbol"] for r in rows], e4["acquisition_run_id"]
        )
        stale = str(e4["asof_date"]) != session
        lines.append(f"Universe: {len(features)} symbols with indicators ({total} scanned)")
        if stale:
            lines.append(f"Indicator scan is as of {e4['asof_date']}, not {session}.")
        lines.append("Market breadth:")
        lines.extend(_breadth(features))
        near = [
            (s, f["distance_from_high"]) for s, f in features.items()
            if f.get("distance_from_high") is not None
        ]
        near.sort(key=lambda item: item[1])
        if near:
            lines.append("Closest to 252-bar high (descriptive, not a signal):")
            lines.extend(f"  {s}: {d:.2f}% below" for s, d in near[:NEAR_HIGH_COUNT])

    lines += ["", DISCLAIMER]
    return "\n".join(lines)[:TELEGRAM_MAX_CHARS]

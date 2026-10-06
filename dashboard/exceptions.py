"""Context builder for the Exceptions view, shared by the JSON route (and later the HTML page).

Descriptive only: lists the symbols of the latest COMPLETE full run that carry a status or a flag,
with filters, three plain sort columns and pagination. No score, rank, band, signal or quality
ordering. It only runs SELECTs on a connection the caller opened read-only and never imports sqlite3.

Layer: everything here is the ScanRun layer (symbol_scan_results / scan_runs).
"""
from __future__ import annotations

import math
from typing import Optional
from urllib.parse import quote, urlencode

from dashboard import queries, review_file, stock_detail

DEFAULT_CATEGORY = "FAILED"
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200
MAX_TEXT_LENGTH = 100
SORT_COLUMNS = ("symbol", "company_name", "sector")  # plain columns only; nothing that implies quality
SORT_DIRECTIONS = ("asc", "desc")
FLAGS_NOT_EVALUATED_FOR_FAILED = "flags other than NON_EQ_SERIES are not evaluated for a FAILED symbol"

# The 7 categories: (kind, key, column). kind "status" filters symbol_data_status = key;
# kind "flag" filters the whitelisted flag column (key is the queries.FLAG_COLUMNS key).
CATEGORY_COLUMNS = {
    "FAILED": ("status", "FAILED", "symbol_data_status"),
    "STALE": ("status", "STALE", "symbol_data_status"),
    "INSUFFICIENT_HISTORY": ("status", "INSUFFICIENT_HISTORY", "symbol_data_status"),
    "HISTORY_GAPS": ("flag", "history_gaps", "history_gaps_flag"),
    "NON_EQ_SERIES": ("flag", "non_eq_series", "non_eq_series_flag"),
    "PRICE_BREAK_DETECTED": ("flag", "price_break_detected", "price_break_detected_flag"),
    "CORPORATE_ACTION_REVIEW": ("flag", "corporate_action_review", "corporate_action_review_flag"),
}


def _check_category_table() -> None:
    for name, (kind, key, column) in CATEGORY_COLUMNS.items():
        if kind == "status":
            ok = key in queries.STATUS_VALUES and column == "symbol_data_status"
        else:
            ok = queries.FLAG_COLUMNS.get(key) == column
        if not ok:
            raise RuntimeError(f"CATEGORY_COLUMNS[{name!r}] does not match the queries.py whitelists")


_check_category_table()


class ParamError(ValueError):
    """An invalid query parameter; the route turns it into a 400 with this plain message."""


def _positive_int(args, name: str, default: int, maximum: Optional[int] = None) -> int:
    raw = args.get(name)
    if raw is None or raw == "":
        return default
    if not (raw.isascii() and raw.isdigit()) or int(raw) < 1:
        raise ParamError(f"{name} must be a positive whole number, got {raw!r}")
    value = int(raw)
    if maximum is not None and value > maximum:
        raise ParamError(f"{name} must be at most {maximum}, got {value}")
    return value


def _text(args, name: str) -> Optional[str]:
    raw = args.get(name)
    if raw is None or raw == "":
        return None
    if len(raw) > MAX_TEXT_LENGTH:
        raise ParamError(f"{name} must be at most {MAX_TEXT_LENGTH} characters")
    return raw


def parse_params(args) -> dict:
    """Validate the query string. Unknown or invalid VALUES raise ParamError (never silently reset)."""
    category = args.get("category") or DEFAULT_CATEGORY
    if category not in CATEGORY_COLUMNS:
        raise ParamError(f"category must be one of {', '.join(CATEGORY_COLUMNS)}, got {category!r}")
    sort = args.get("sort") or "symbol"
    if sort not in SORT_COLUMNS:
        raise ParamError(f"sort must be one of {', '.join(SORT_COLUMNS)}, got {sort!r}")
    direction = (args.get("dir") or "asc")
    if direction not in SORT_DIRECTIONS:
        raise ParamError(f"dir must be asc or desc, got {direction!r}")
    changed = args.get("changed") or "0"
    if changed not in ("0", "1"):
        raise ParamError(f"changed must be 0 or 1, got {changed!r}")
    return {
        "category": category,
        "q": _text(args, "q"),
        "sector": _text(args, "sector"),
        "changed": changed == "1",
        "page": _positive_int(args, "page", 1),
        "page_size": _positive_int(args, "page_size", DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
        "sort": sort,
        "dir": direction,
    }


def _previous_rows(conn, previous_run_id: str, symbols: list) -> dict:
    columns = ", ".join(queries.FLAG_COLUMNS.values())  # whitelist, never user input
    found: dict = {}
    for start in range(0, len(symbols), 400):  # stay well under SQLite's bound-variable limit
        chunk = symbols[start : start + 400]
        marks = ",".join(["?"] * len(chunk))
        for row in queries._fetch_all_dicts(
            conn,
            f"SELECT symbol, symbol_data_status, {columns} FROM symbol_scan_results "
            f"WHERE scan_run_id = ? AND symbol IN ({marks})",
            [previous_run_id, *chunk],
        ):
            found[row["symbol"]] = row
    return found


def _marker(row: dict, previous: Optional[dict], has_previous_run: bool) -> dict:
    """What differs from the previous COMPLETE full run: status and flags only, never counts.

    A symbol absent from the previous run is "new", never "changed". A FAILED symbol was never
    evaluated for flags other than NON_EQ_SERIES, so when either side is FAILED only that flag
    (and the status) is compared.
    """
    if not has_previous_run:
        return {"state": "no_previous_run", "changes": [], "text": "no previous COMPLETE run to compare"}
    if previous is None:
        return {"state": "new", "changes": [], "text": "new in this run"}
    changes = []
    if row["symbol_data_status"] != previous["symbol_data_status"]:
        changes.append(f"status {previous['symbol_data_status']}->{row['symbol_data_status']}")
    either_failed = "FAILED" in (row["symbol_data_status"], previous["symbol_data_status"])
    for name, column in queries.FLAG_COLUMNS.items():
        if either_failed and name != "non_eq_series":
            continue
        was, now = bool(previous[column]), bool(row[column])
        if now and not was:
            changes.append(f"flag {name.upper()} added")
        elif was and not now:
            changes.append(f"flag {name.upper()} removed")
    return {"state": "changed" if changes else "unchanged", "changes": changes,
            "text": "; ".join(changes) if changes else "unchanged"}


def _row_view(row: dict, marker: dict) -> dict:
    return {
        "symbol": row["symbol"],
        "company_name": row["company_name"],
        "sector": row["sector"],
        "status": row["symbol_data_status"],
        "status_reason": row["status_reason"],
        "available_session_count": row["available_session_count"],
        "missing_session_count": row["missing_session_count"],
        "flags": {name.upper(): bool(row[column]) for name, column in queries.FLAG_COLUMNS.items()},
        "changed_since_previous": marker,
        "stock_url": f"/equity/stock/{quote(row['symbol'], safe='')}",
    }


PAGE_PATH = "/equity/exceptions"


def page_url(params: dict, **changes) -> str:
    """The Exceptions page URL for `params` with `changes` applied. Every non-default value is kept in
    the query string (category always), so any view can be bookmarked and reopened identically."""
    merged = {**params, **changes}
    pairs = [("category", merged["category"])]
    if merged["q"]:
        pairs.append(("q", merged["q"]))
    if merged["sector"]:
        pairs.append(("sector", merged["sector"]))
    if merged["changed"]:
        pairs.append(("changed", "1"))
    if merged["page"] != 1:
        pairs.append(("page", str(merged["page"])))
    if merged["page_size"] != DEFAULT_PAGE_SIZE:
        pairs.append(("page_size", str(merged["page_size"])))
    if merged["sort"] != "symbol":
        pairs.append(("sort", merged["sort"]))
    if merged["dir"] != "asc":
        pairs.append(("dir", merged["dir"]))
    return f"{PAGE_PATH}?{urlencode(pairs)}"


def page_links(body: dict) -> dict:
    """All links of the HTML page, built from the validated params. Changing the category, a filter or a
    sort goes back to page 1; the page links keep everything else."""
    p = body["params"]
    last = body["total_pages"]
    sort_links = {}
    for column in SORT_COLUMNS:
        active = p["sort"] == column
        direction = "desc" if active and p["dir"] == "asc" else "asc"
        sort_links[column] = {"url": page_url(p, sort=column, dir=direction, page=1), "active": active,
                              "dir": p["dir"] if active else None}
    return {
        "categories": {name: page_url(p, category=name, page=1) for name in CATEGORY_COLUMNS},
        "sort": sort_links,
        "prev": page_url(p, page=p["page"] - 1) if p["page"] > 1 else None,
        "next": page_url(p, page=p["page"] + 1) if p["page"] < last else None,
        "clear_filters": page_url(p, q=None, sector=None, changed=False, page=1),
        "changed_on": page_url(p, changed=True, page=1),
        "changed_off": page_url(p, changed=False, page=1),
        "this_page": page_url(p),
    }


def _comparability_notes(latest: dict, previous: Optional[dict]) -> list:
    if previous is None:
        return []
    notes = []
    for field, effect in (
        ("universe_version", "symbols may be new or missing because the constituent list changed"),
        ("corporate_action_review_version",
         "CORPORATE_ACTION_REVIEW changes may come from an edit of the review file, not from the data"),
    ):
        if latest.get(field) != previous.get(field):
            notes.append(f"{field} differs from the previous COMPLETE run "
                         f"({_short(latest.get(field))} vs {_short(previous.get(field))}): {effect}")
    return notes


def _short(value) -> str:
    return "not recorded" if not value else str(value)[:12]


REVIEW_CATEGORY = "CORPORATE_ACTION_REVIEW"
FLAG_RULE = ("an entry flags a symbol only when it is not RESOLVED and its effective_date falls inside "
             "the symbol's fetched window")


def review_panel(conn, body: dict, demo: bool) -> Optional[dict]:
    """The review-file panel for the CORPORATE_ACTION_REVIEW category, else None.

    Reads data/reference/corporate_action_review.csv (read-only, via the shared reader) and says what the
    file contains NOW. A header-only file is "review file empty: no symbols reviewed", never "0 issues".
    The demo database is fabricated, so its page does not read the real file. `body` comes from build().
    """
    if body.get("category") != REVIEW_CATEGORY or body.get("run") is None:
        return None
    run = body["run"]
    flagged = body["counts"]["recount"]["flags"]["CORPORATE_ACTION_REVIEW"]
    panel = {"file_state": None, "message": None, "version_note": None, "entries": [], "total_entries": 0,
             "flagged_in_run": flagged, "flag_rule": FLAG_RULE, "consistency_note": None}
    if demo:
        panel["file_state"] = "not_read_demo"
        panel["message"] = "review file is not read in demo mode (demo data is fabricated)"
        return panel
    state = review_file.read_review_file(stock_detail.review_csv_path(), run["corporate_action_review_version"])
    panel["file_state"], panel["message"] = state["file_state"], state["message"]
    panel["version_note"] = state.get("version_note")
    entries = state["entries"]
    panel["total_entries"] = len(entries)
    symbols = sorted({e.symbol for e in entries})
    in_run: dict = {}
    for start in range(0, len(symbols), 400):
        chunk = symbols[start : start + 400]
        for row in queries._fetch_all_dicts(
            conn,
            "SELECT symbol, corporate_action_review_flag FROM symbol_scan_results "
            f"WHERE scan_run_id = ? AND symbol IN ({','.join(['?'] * len(chunk))})",
            [run["run_id"], *chunk],
        ):
            in_run[row["symbol"]] = bool(row["corporate_action_review_flag"])
    panel["entries"] = [
        {**e.__dict__, "in_run": e.symbol in in_run, "flagged_in_run": in_run.get(e.symbol),
         "stock_url": f"/equity/stock/{quote(e.symbol, safe='')}" if e.symbol in in_run else None}
        for e in entries
    ]
    if state["file_state"] != "has_entries" and flagged:
        panel["consistency_note"] = (
            f"{flagged} symbol(s) are flagged in run {run['run_id']}, but the current review file has no "
            "entries to show: it may have been edited after the run")
    elif state["file_state"] == "has_entries" and not flagged:
        panel["consistency_note"] = (
            f"the file has {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, but no symbol is flagged in "
            f"run {run['run_id']}: {FLAG_RULE}")
    return panel


def build(conn, params: dict) -> dict:
    """The Exceptions payload for the latest COMPLETE full run. `params` comes from parse_params."""
    latest = queries.get_latest_complete_run(conn)
    if latest is None:
        return {"run": None, "message": "no COMPLETE scan run yet"}
    run_id = latest["run_id"]
    previous = queries.get_previous_complete_run(conn, latest)
    counts = queries.get_exception_counts(conn, run_id)
    category = params["category"]
    kind, key, _column = CATEGORY_COLUMNS[category]
    filters = {
        "q": params["q"], "sector": params["sector"],
        "status": key if kind == "status" else None, "flag": key if kind == "flag" else None,
        "sort": params["sort"], "sort_dir": params["dir"], "escape_like": True,
    }
    page, page_size = params["page"], params["page_size"]
    notice = None

    if params["changed"] and previous is None:
        total, page_rows, markers = 0, [], {}
        notice = "the changed filter needs a previous COMPLETE run, and none exists"
    elif params["changed"]:
        matching, _ = queries.get_candidates(conn, run_id, 1, 1, **filters)
        _, every_row = queries.get_candidates(conn, run_id, 1, max(matching, 1), **filters)
        prior = _previous_rows(conn, previous["run_id"], [r["symbol"] for r in every_row])
        changed = [(r, _marker(r, prior.get(r["symbol"]), True)) for r in every_row]
        changed = [(r, m) for r, m in changed if m["state"] == "changed"]
        total = len(changed)
        window = changed[(page - 1) * page_size : page * page_size]
        page_rows = [r for r, _ in window]
        markers = {r["symbol"]: m for r, m in window}
    else:
        total, page_rows = queries.get_candidates(conn, run_id, page, page_size, **filters)
        prior = _previous_rows(conn, previous["run_id"], [r["symbol"] for r in page_rows]) if previous else {}
        markers = {r["symbol"]: _marker(r, prior.get(r["symbol"]), previous is not None) for r in page_rows}

    evaluated = counts["evaluated"]
    narrowed = bool(params["q"] or params["sector"] or params["changed"])
    if total == 0 and notice is None:
        notice = (f"no symbols with {category} match the current filters in run {run_id} ({evaluated} evaluated)"
                  if narrowed else f"no symbols with {category} in run {run_id} ({evaluated} evaluated)")

    failed_symbols = counts["recount"]["status"]["FAILED"]
    failed_note = None
    if kind == "flag" and key != "non_eq_series":
        failed_note = (f"{failed_symbols} FAILED symbol(s) were not evaluated for {category}: "
                       f"{FLAGS_NOT_EVALUATED_FOR_FAILED}")
    return {
        "run": {
            "run_id": run_id, "started_at": latest["started_at"], "finished_at": latest["finished_at"],
            "latest_closed_session": latest["latest_closed_session"],
            "universe_version": latest["universe_version"],
            "corporate_action_review_version": latest["corporate_action_review_version"],
        },
        "previous_run": None if previous is None else {"run_id": previous["run_id"], "started_at": previous["started_at"]},
        "scoring_status": "BLOCKED_B2",
        "params": params,
        "category": category,
        "category_counts": {**{name: counts["recount"]["status"][k] for name, (kind_, k, _) in CATEGORY_COLUMNS.items()
                               if kind_ == "status"},
                            **{name: counts["recount"]["flags"][k.upper()] for name, (kind_, k, _) in CATEGORY_COLUMNS.items()
                               if kind_ == "flag"}},
        "counts": counts,
        "counts_rule": "recount equals stored run counts",
        "evaluated": evaluated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
        "rows": [_row_view(r, markers[r["symbol"]]) for r in page_rows],
        "notice": notice,
        "failed_note": failed_note,
        "newer_run": stock_detail.get_newer_non_complete_run(conn, latest),
        "comparability_notes": _comparability_notes(latest, previous),
    }

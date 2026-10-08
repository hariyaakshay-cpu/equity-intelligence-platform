"""Context builder for the Snapshot Audit view (JSON route now, HTML page later).

Compares the STORED price_fetch_snapshots of two COMPLETE full runs and reports "bars whose stored hash
differs". Descriptive only: no score, rank, band or signal, no sort by how many bars differ, and no claim about
why a bar differs. The main view (build) recomputes no hash: the only comparison is string equality of two
stored content_hash values, done in SQL by queries.get_revision_summary. The one place a hash is recomputed is
the per-symbol drill-down (build_symbol), through stored_row_integrity.check_rows over that symbol's stored bars
only. It only runs SELECTs on a connection the caller opened read-only and never imports sqlite3.

Layer: everything here is the ScanRun layer (scan_runs / symbol_scan_results / price_fetch_snapshots).
"""
from __future__ import annotations

import math
from typing import Optional
from urllib.parse import quote, urlencode

from dashboard import queries, stock_detail, stored_row_integrity

DEFAULT_VIEW = "revised"
VIEWS = ("revised", "added", "removed")
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200
MAX_TEXT_LENGTH = 100
SORT_COLUMNS = ("symbol", "company_name", "sector")  # plain columns only; never the number of differing bars
SORT_DIRECTIONS = ("asc", "desc")
PAGE_PATH = "/equity/snapshot-audit"
SYMBOL_PATH = PAGE_PATH + "/symbol"
VALUE_FIELDS = ("open", "high", "low", "close", "volume")  # the stored values shown side by side
SAME_VALUES_NOTE = "stored hash differs although the displayed values are equal; this page does not explain why"
INTEGRITY_NOTE = ("Checks that stored bars match their stored hash. It does not prove the vendor data is unchanged; "
                  "vendor revisions are detected by comparing the two runs above.")
ADJUSTMENT_NOTE = "Values are shown as stored when retrieved. The adjustment basis is NOT_DEFINED; this page does not adjust or compute any value."

METRIC_NAME = "bars whose stored hash differs"
METRIC_NOTE = (
    "A bar is one trading date of one symbol from one source. It is counted here when both runs store it and the "
    "stored content_hash differs. That can be a possible vendor revision, but this page does not classify the "
    "cause, and the adjustment basis is NOT_DEFINED. Bars stored by only one run are not revisions."
)
NO_HASH_VERSION_NOTE = (
    "scan_runs records no hash or quantisation version (the rule, 2 decimal places with ROUND_HALF_UP, lives in "
    "code and in spec section 8). If that rule had changed between two runs, every overlapping bar would differ, "
    "and the stored data could not tell you."
)
ONE_SIDED_NOTE = (
    "Bars stored by only one run are counted separately and are not revisions. The bar totals cover comparable "
    "symbols only: a symbol that is FAILED, or has no stored bars, in either run cannot be compared bar by bar."
)
_KIND_LABELS = {"ABORTED": "ABORTED", "RUNNING": "RUNNING", "SMOKE": "smoke run, --symbols"}


class ParamError(ValueError):
    """An invalid query parameter or run selection; the route turns it into a 400 with this plain message."""


# ---------------------------------------------------------------- parameters

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


def _pair(args) -> tuple[Optional[str], Optional[str]]:
    base, other = _text(args, "base"), _text(args, "other")
    if (base is None) != (other is None):
        raise ParamError("base and other must be given together (or both left out to use the two newest runs)")
    return base, other


def parse_symbol_params(args) -> dict:
    """The drill-down takes the same two run selectors as the main page and nothing else."""
    base, other = _pair(args)
    return {"base": base, "other": other}


def parse_params(args) -> dict:
    """Validate the query string. Invalid VALUES raise ParamError (never silently reset to a default).

    `base` and `other` are the only run selectors: both or neither (neither means the default pair). Whether
    they name eligible runs is checked in build(), which has the database.
    """
    view = args.get("view") or DEFAULT_VIEW
    if view not in VIEWS:
        raise ParamError(f"view must be one of {', '.join(VIEWS)}, got {view!r}")
    sort = args.get("sort") or "symbol"
    if sort not in SORT_COLUMNS:
        raise ParamError(f"sort must be one of {', '.join(SORT_COLUMNS)}, got {sort!r}")
    direction = args.get("dir") or "asc"
    if direction not in SORT_DIRECTIONS:
        raise ParamError(f"dir must be asc or desc, got {direction!r}")
    base, other = _pair(args)
    return {
        "base": base, "other": other, "view": view, "q": _text(args, "q"), "sector": _text(args, "sector"),
        "page": _positive_int(args, "page", 1),
        "page_size": _positive_int(args, "page_size", DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
        "sort": sort, "dir": direction,
    }


# ---------------------------------------------------------------- choosing the two runs

def _eligible_run(conn, run_id: str) -> dict:
    """The full scan_runs row of `run_id`, or ParamError saying why it cannot be compared."""
    run = queries.get_run(conn, run_id)
    if run is None:
        raise ParamError(f"run {run_id} does not exist")
    if run["status"] != "COMPLETE" or run["symbols_filter_json"] is not None:
        kind, _reason = queries._ineligible_reason(run)
        raise ParamError(f"run {run_id} is not a COMPLETE full run ({_KIND_LABELS[kind]})")
    return run


def _older_first(a: dict, b: dict) -> tuple[dict, dict]:
    """Order two runs by (started_at, run_id): the smaller is the older one."""
    return (a, b) if (a["started_at"], a["run_id"]) <= (b["started_at"], b["run_id"]) else (b, a)


def _choose_pair(conn, params: dict) -> tuple[Optional[dict], Optional[dict], bool, Optional[str]]:
    """(older, newer, swapped, swap_note). Both None when fewer than two eligible runs exist and none was named."""
    if params["base"] is not None:
        if params["base"] == params["other"]:
            raise ParamError(f"base and other are the same run ({params['base']}); a comparison needs two different runs")
        given_base = _eligible_run(conn, params["base"])
        given_other = _eligible_run(conn, params["other"])
        older, newer = _older_first(given_base, given_other)
        swapped = older["run_id"] != given_base["run_id"]
        note = None
        if swapped:
            note = (f"base ({given_base['run_id']}) is newer than other ({given_other['run_id']}), so the two were "
                    f"swapped: the older run {older['run_id']} is used as base and the newer run {newer['run_id']} as other")
        return older, newer, swapped, note
    eligible = queries.get_eligible_runs(conn, limit=2)["runs"]  # newest first, same order as get_previous_complete_run
    if len(eligible) < 2:
        return None, None, False, None
    return queries.get_run(conn, eligible[1]["run_id"]), queries.get_run(conn, eligible[0]["run_id"]), False, None


def _short(value) -> str:
    return "not recorded" if not value else str(value)[:12]


def _run_view(run: dict) -> dict:
    return {key: run[key] for key in ("run_id", "started_at", "finished_at", "latest_closed_session",
                                      "universe_version", "corporate_action_review_version", "git_commit")}


def _comparability_notes(older: dict, newer: dict) -> list:
    notes = []
    for field, effect in (
        ("universe_version", "symbols may be added or removed because the constituent list changed"),
        ("corporate_action_review_version", "CORPORATE_ACTION_REVIEW flags may differ because the review file was edited"),
        ("git_commit", "the scanner code that produced the two runs differs"),
    ):
        if older.get(field) != newer.get(field):
            notes.append(f"{field} differs between the two runs ({_short(older.get(field))} vs {_short(newer.get(field))}): {effect}")
    notes.append(NO_HASH_VERSION_NOTE)
    return notes


# ---------------------------------------------------------------- rows for the views

def _matches(row: dict, q: Optional[str], sector: Optional[str]) -> bool:
    if q:
        needle = q.lower()  # like SQL LIKE for ASCII: case-insensitive, and % and _ are plain characters
        if needle not in (row["symbol"] or "").lower() and needle not in (row["company_name"] or "").lower():
            return False
    if sector == "UNKNOWN":  # UNKNOWN means no sector is stored
        return row["sector"] is None
    if sector:
        return row["sector"] == sector
    return True


def _sorted_like_sql(rows: list, sort: str, direction: str) -> list:
    """Order rows as the SQL views do: a plain column (binary comparison), rows with no value last in either
    direction, and symbol ascending as the tie-break."""
    present = sorted((r for r in rows if r[sort] is not None), key=lambda r: r["symbol"])
    present.sort(key=lambda r: r[sort], reverse=direction == "desc")  # a stable sort keeps symbol order among equals
    return present + sorted((r for r in rows if r[sort] is None), key=lambda r: r["symbol"])


def drilldown_url(symbol: str, base: str, other: str) -> str:
    """The per-symbol page for the RESOLVED pair, so a link never moves to a newer pair."""
    return f"{SYMBOL_PATH}/{quote(symbol, safe='')}?{urlencode([('base', base), ('other', other)])}"


def _revised_rows(summary_symbols: list, params: dict, base: str, other: str) -> tuple[int, list]:
    """Comparable symbols with at least one differing bar, filtered, sorted by a plain column, one page of them."""
    rows = [r for r in summary_symbols if r["comparable"] and r["differing"] > 0 and _matches(r, params["q"], params["sector"])]
    rows = _sorted_like_sql(rows, params["sort"], params["dir"])
    start = (params["page"] - 1) * params["page_size"]
    page = rows[start : start + params["page_size"]]
    return len(rows), [
        {"symbol": r["symbol"], "company_name": r["company_name"], "sector": r["sector"],
         "overlapping_bars": r["overlapping"], "differing_bars": r["differing"],
         "first_differing_date": r["first_differing_date"], "last_differing_date": r["last_differing_date"],
         "bars_older_run": r["bars_base"], "bars_newer_run": r["bars_other"],
         "stock_url": f"/equity/stock/{quote(r['symbol'], safe='')}", "drilldown_url": drilldown_url(r["symbol"], base, other)}
        for r in page
    ]


def _set_rows(conn, older: dict, newer: dict, params: dict) -> tuple[int, list]:
    diff = queries.get_symbol_set_diff(
        conn, older["run_id"], newer["run_id"], view=params["view"], q=params["q"], sector=params["sector"],
        sort=params["sort"], sort_dir=params["dir"], page=params["page"], page_size=params["page_size"])
    return diff["total"], [
        {"symbol": r["symbol"], "company_name": r["company_name"], "sector": r["sector"], "status": r["symbol_data_status"],
         "status_reason": r["status_reason"], "stock_url": f"/equity/stock/{quote(r['symbol'], safe='')}"}
        for r in diff["rows"]
    ]


def _counts_text(counts: dict) -> dict:
    return {
        "differing": (f"{counts['differing_bars']} of {counts['overlapping_bars']} overlapping bars differ "
                      f"({METRIC_NAME}), across {counts['comparable_symbols']} comparable symbols"),
        "symbols_with_differing": (f"{counts['symbols_with_differing_bars']} of {counts['comparable_symbols']} "
                                   "comparable symbols have at least one such bar"),
        "one_sided": (f"{counts['only_in_older']} bars are only in the older run and {counts['only_in_newer']} are only "
                      "in the newer run (comparable symbols only)"),
        "not_comparable": (f"{counts['not_comparable_symbols']} of {counts['in_both']} symbols present in both runs "
                           "cannot be compared bar by bar (FAILED, or no stored bars)"),
        "added_removed": (f"{counts['added']} symbols added and {counts['removed']} removed "
                          f"({counts['in_both']} in both runs)"),
    }


def _empty_notice(view: str, params: dict, counts: dict, older: dict, newer: dict) -> str:
    narrowed = bool(params["q"] or params["sector"])
    if view == "revised":
        base = (f"{counts['overlapping_bars']} overlapping bars were compared across {counts['comparable_symbols']} "
                f"comparable symbols between run {older['run_id']} and run {newer['run_id']}")
        return (f"no comparable symbols match the current filters ({base})" if narrowed
                else f"no comparable symbol has bars whose stored hash differs ({base})")
    word = "added to" if view == "added" else "removed from"
    scope = f"{counts['symbols_other']} symbols in the newer run, {counts['symbols_base']} in the older run"
    return (f"no symbols {word} the universe match the current filters ({scope})" if narrowed
            else f"no symbols were {view} between run {older['run_id']} and run {newer['run_id']} ({scope})")


# ---------------------------------------------------------------- the payload

def build(conn, params: dict) -> dict:
    """The Snapshot Audit payload. `params` comes from parse_params; a bad run selection raises ParamError."""
    older, newer, swapped, swap_note = _choose_pair(conn, params)
    body: dict = {
        "scoring_status": "BLOCKED_B2",
        "layer": "ScanRun",
        "metric": {"name": METRIC_NAME, "note": METRIC_NOTE},
        "params": params,
        "eligible_runs": queries.get_eligible_runs(conn),
        "ineligible_runs": queries.get_ineligible_runs(conn),
    }
    if older is None:
        found = body["eligible_runs"]["total"]
        body.update({
            "comparison_available": False,
            "message": f"a comparison needs two COMPLETE full runs; found {found}",
            "base_run": None, "other_run": None, "swapped": False, "swap_note": None, "comparability_notes": [],
            "counts": None, "counts_text": None, "one_sided_note": ONE_SIDED_NOTE, "views": None,
            "view": params["view"], "rows": [], "total": 0, "page": params["page"], "page_size": params["page_size"],
            "total_pages": 0, "notice": None, "newer_run": None,
        })
        return body

    summary = queries.get_revision_summary(conn, older["run_id"], newer["run_id"])
    counts = summary["counts"]
    view = params["view"]
    total, rows = _revised_rows(summary["symbols"], params, older["run_id"], newer["run_id"]) if view == "revised" else _set_rows(conn, older, newer, params)
    body.update({
        "comparison_available": True,
        "message": None,
        "base_run": _run_view(older),
        "other_run": _run_view(newer),
        "swapped": swapped,
        "swap_note": swap_note,
        "comparability_notes": _comparability_notes(older, newer),
        "counts": counts,
        "counts_text": _counts_text(counts),
        "one_sided_note": ONE_SIDED_NOTE,
        "views": {"revised": counts["symbols_with_differing_bars"], "added": counts["added"], "removed": counts["removed"]},
        "view": view,
        "rows": rows,
        "total": total,
        "page": params["page"],
        "page_size": params["page_size"],
        "total_pages": math.ceil(total / params["page_size"]),
        "notice": _empty_notice(view, params, counts, older, newer) if total == 0 else None,
        "newer_run": stock_detail.get_newer_non_complete_run(conn, newer),
    })
    return body


# ---------------------------------------------------------------- links for the HTML page (used by the next commit)

def page_url(params: dict, base: str, other: str, **changes) -> str:
    """The page URL for `params` with `changes` applied. The two RESOLVED run ids are always kept, so a bookmark
    or a page link never moves to a newer pair when another run completes. Other non-default values are kept too."""
    merged = {**params, **changes}
    pairs = [("base", base), ("other", other)]
    if merged["view"] != DEFAULT_VIEW:
        pairs.append(("view", merged["view"]))
    if merged["q"]:
        pairs.append(("q", merged["q"]))
    if merged["sector"]:
        pairs.append(("sector", merged["sector"]))
    if merged["page"] != 1:
        pairs.append(("page", str(merged["page"])))
    if merged["page_size"] != DEFAULT_PAGE_SIZE:
        pairs.append(("page_size", str(merged["page_size"])))
    if merged["sort"] != "symbol":
        pairs.append(("sort", merged["sort"]))
    if merged["dir"] != "asc":
        pairs.append(("dir", merged["dir"]))
    return f"{PAGE_PATH}?{urlencode(pairs)}"


def page_links(body: dict) -> Optional[dict]:
    """All links of the HTML page from a build() payload, or None when no comparison is available. Changing the
    view, a filter or a sort goes back to page 1; page links keep everything else."""
    if not body["comparison_available"]:
        return None
    p = body["params"]
    base, other = body["base_run"]["run_id"], body["other_run"]["run_id"]
    sort_links = {}
    for column in SORT_COLUMNS:
        active = p["sort"] == column
        direction = "desc" if active and p["dir"] == "asc" else "asc"
        sort_links[column] = {"url": page_url(p, base, other, sort=column, dir=direction, page=1), "active": active,
                              "dir": p["dir"] if active else None}
    return {
        "views": {name: page_url(p, base, other, view=name, page=1) for name in VIEWS},
        "sort": sort_links,
        "prev": page_url(p, base, other, page=p["page"] - 1) if p["page"] > 1 else None,
        "next": page_url(p, base, other, page=p["page"] + 1) if p["page"] < body["total_pages"] else None,
        "clear_filters": page_url(p, base, other, q=None, sector=None, page=1),
        "this_page": page_url(p, base, other),
    }


# ---------------------------------------------------------------- the per-symbol drill-down

def _as_text(value) -> Optional[str]:
    return None if value is None else str(value)


def _side(result: Optional[dict], bars: list) -> dict:
    return {"present": result is not None, "status": result["symbol_data_status"] if result else None,
            "status_reason": result["status_reason"] if result else None, "stored_bars": len(bars)}


def _integrity(present: bool, bars: list) -> dict:
    """The stored-row integrity of one run's bars of this symbol: the only hash recompute in Phase 3."""
    check = stored_row_integrity.check_rows(bars)  # one recompute per stored bar of THIS symbol in THIS run
    if not present:
        detail = "the symbol is not in this run"
    elif check["state"] == "UNAVAILABLE":
        detail = "no stored bars to check"
    elif check["state"] == "MISMATCH":
        shown = ", ".join(check["mismatched"][:5]) + (", ..." if len(check["mismatched"]) > 5 else "")
        detail = f"{len(check['mismatched'])} of {check['bars']} stored bars do not reproduce their stored hash ({shown})"
    else:
        detail = f"all {check['bars']} stored bars reproduce their stored hash"
    return {**check, "detail": detail}


def _side_by_side(row: dict) -> dict:
    base = {f: row[f"base_{f}"] for f in VALUE_FIELDS}
    other = {f: row[f"other_{f}"] for f in VALUE_FIELDS}
    differing = [f for f in VALUE_FIELDS if _as_text(base[f]) != _as_text(other[f])]  # compared as stored text
    return {"trading_date": row["trading_date"], "source": row["source"], "base": base, "other": other,
            "differing_fields": differing, "note": None if differing else SAME_VALUES_NOTE}


def build_symbol(conn, params: dict, symbol: str) -> dict:
    """The drill-down payload for one symbol. `params` comes from parse_symbol_params; a bad run selection or an
    over-long symbol raises ParamError. `state` is comparable, not_comparable, added, removed or absent."""
    if len(symbol) > MAX_TEXT_LENGTH:
        raise ParamError(f"symbol must be at most {MAX_TEXT_LENGTH} characters")
    older, newer, swapped, swap_note = _choose_pair(conn, params)
    body: dict = {
        "scoring_status": "BLOCKED_B2", "layer": "ScanRun", "metric": {"name": METRIC_NAME, "note": METRIC_NOTE},
        "params": params, "symbol": symbol, "comparison_available": older is not None, "message": None, "state": None,
        "base_run": None, "other_run": None, "swapped": swapped, "swap_note": swap_note, "comparability_notes": [],
        "company_name": None, "sector": None, "base_symbol": None, "other_symbol": None, "reason": None,
        "counts": None, "counts_text": None, "rows": [], "cap": queries.REVISION_ROW_CAP, "truncated": False,
        "truncation_notice": None, "integrity": None, "integrity_note": INTEGRITY_NOTE, "adjustment_note": ADJUSTMENT_NOTE,
        "no_overlap_note": None, "stock_url": f"/equity/stock/{quote(symbol, safe='')}",
    }
    if older is None:
        found = queries.get_eligible_runs(conn)["total"]
        body["message"] = f"a comparison needs two COMPLETE full runs; found {found}"
        return body
    old_id, new_id = older["run_id"], newer["run_id"]
    base_result, other_result = queries.get_symbol_result(conn, old_id, symbol), queries.get_symbol_result(conn, new_id, symbol)
    base_bars, other_bars = queries.get_stored_bars(conn, old_id, symbol), queries.get_stored_bars(conn, new_id, symbol)
    present = base_result or other_result
    body.update({
        "base_run": _run_view(older), "other_run": _run_view(newer), "comparability_notes": _comparability_notes(older, newer),
        "company_name": present["company_name"] if present else None, "sector": present["sector"] if present else None,
        "base_symbol": _side(base_result, base_bars), "other_symbol": _side(other_result, other_bars),
    })
    if other_result is not None:
        body.update({"company_name": other_result["company_name"], "sector": other_result["sector"]})
    if present is None:
        body.update({"state": "absent", "message": f"symbol {symbol} is in neither run ({old_id} nor {new_id})"})
        return body
    body["integrity"] = {"base": _integrity(base_result is not None, base_bars), "other": _integrity(other_result is not None, other_bars)}
    if base_result is None or other_result is None:
        state, where = ("added", f"in the newer run {new_id} but not in the older run {old_id}") if base_result is None \
            else ("removed", f"in the older run {old_id} but not in the newer run {new_id}")
        body.update({"state": state, "message": f"{symbol} was {state}: it is {where}. There is nothing to compare bar by bar."})
        return body
    reason = queries._not_comparable_reason({
        "base_status": base_result["symbol_data_status"], "other_status": other_result["symbol_data_status"],
        "bars_base": len(base_bars), "bars_other": len(other_bars)})
    if reason is not None:
        body.update({"state": "not_comparable", "reason": reason, "message": f"{symbol} cannot be compared bar by bar: {reason}"})
        return body
    revisions = queries.get_symbol_revisions(conn, old_id, new_id, symbol, newest_first=True)
    differing, overlapping = revisions["differing"], revisions["overlapping"]
    body.update({
        "state": "comparable",
        "counts": {"overlapping_bars": overlapping, "differing_bars": differing,
                   "only_in_older": revisions["only_in_older"], "only_in_newer": revisions["only_in_newer"]},
        "counts_text": {
            "differing": f"{differing} of {overlapping} overlapping bars differ ({METRIC_NAME})",
            "one_sided": (f"{revisions['only_in_older']} bars are only in the older run and "
                          f"{revisions['only_in_newer']} are only in the newer run"),
        },
        "rows": [_side_by_side(r) for r in revisions["rows"]],
        "cap": revisions["cap"], "truncated": revisions["truncated"],
        "truncation_notice": (f"truncated at {revisions['cap']} of {differing} differing bars: the {revisions['cap']} newest are shown"
                              if revisions["truncated"] else None),
        "no_overlap_note": "the two runs share no bar (trading date and source) for this symbol" if overlapping == 0 else None,
    })
    return body


def symbol_links(body: dict) -> Optional[dict]:
    """Links of the drill-down page, or None when no comparison is available. Both resolved run ids are kept."""
    if not body["comparison_available"]:
        return None
    base, other = body["base_run"]["run_id"], body["other_run"]["run_id"]
    defaults = {"view": DEFAULT_VIEW, "q": None, "sector": None, "page": 1, "page_size": DEFAULT_PAGE_SIZE, "sort": "symbol", "dir": "asc"}
    return {"back": page_url(defaults, base, other), "this_page": drilldown_url(body["symbol"], base, other)}

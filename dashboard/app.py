"""Read-only Flask dashboard for equity_intel's scan results (Phase 4).

Frozen routes: GET /equity (the page) and GET /api/equity/{summary,
candidates, sectors, stock/<symbol>, scan-history} (JSON). There are no
write routes of any kind -- no scan-launch, no watchlist editing -- and
every connection this module opens is
equity_intel.persistence.connection.get_read_only_connection, never the
writable get_connection. /api/equity/candidates doubles as the Stock
Explorer's data source: it always reports scoring_status = "BLOCKED_B2"
and never a rank or composite score, because B2 scoring is not
implemented anywhere in equity_intel (see
equity_intel/contracts/scan_run.py).
"""
from __future__ import annotations

import argparse
import errno
import functools
import math
import socket
import sys
from pathlib import Path
from typing import Optional, Union

from flask import Flask, jsonify, render_template, request

from dashboard import queries
from equity_intel.persistence import connection, db_path_guard
from equity_intel.persistence.schema import SCHEMA_VERSION

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

# Port 5000 is already used by the algo_trader dashboard, which must keep
# running -- this dashboard defaults to a different port so both can run
# at the same time. --port still overrides it.
DEFAULT_PORT = 5050


def _page_params(args) -> tuple[int, int]:
    page = max(_to_int(args.get("page"), 1), 1)
    page_size = args.get("page_size")
    page_size = min(max(_to_int(page_size, DEFAULT_PAGE_SIZE), 1), MAX_PAGE_SIZE)
    return page, page_size


def _to_int(value, default):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class _DatabaseUnavailable(Exception):
    """The configured DB file doesn't exist yet, or has no schema_version
    table yet (never initialized) -- distinct from a DB that exists and is
    initialized but simply has zero scan_runs rows, which each route
    already handles on its own as a normal empty result."""


class _DatabaseVersionMismatch(Exception):
    """The DB's recorded schema_version doesn't match what this dashboard
    (equity_intel.persistence.schema.SCHEMA_VERSION) expects."""

    def __init__(self, found_version) -> None:
        self.found_version = found_version
        super().__init__(f"schema_version {found_version} != expected {SCHEMA_VERSION}")


class _DatabaseError(Exception):
    """The DB file exists but couldn't be opened or read for a reason
    other than "not yet initialized" -- locked, corrupt, a permissions
    problem, or anything else. Deliberately never conflated with
    _DatabaseUnavailable ("no scans yet" is a normal, fine state; this is
    a real problem the operator should see distinctly)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _open_checked_connection(db_path):
    """Open a read-only connection, or raise one of three distinct
    exceptions instead of a 500:

    - _DatabaseUnavailable: no database file exists yet, or it exists but
      has no schema_version table (never initialized). Shown as "no scans
      yet" -- a normal, fine state.
    - _DatabaseVersionMismatch: schema_version doesn't match what this
      dashboard expects.
    - _DatabaseError: the file exists but couldn't be opened/read for any
      other reason (locked, corrupt, permissions).

    A ValueError from db_path_guard (a forbidden/misconfigured path) is
    deliberately NOT caught here: that is a configuration bug, not a
    routine dashboard state, and must fail loudly rather than be
    swallowed into a 200 "no scans yet" response.

    This module never imports sqlite3 itself (see
    equity_intel/tests/test_db_connection_boundary.py). It distinguishes
    "no file at this path" from "file exists but is broken" with
    pathlib.Path.exists() rather than by inspecting sqlite3's own
    exception types -- confirmed empirically that sqlite3, opened in
    read-only URI mode, raises at connect() time for a missing file but
    only at the first execute() for a file that exists but isn't a valid
    database (its header check is lazy).
    """
    try:
        conn = connection.get_read_only_connection(db_path)
    except ValueError:
        raise
    except Exception as exc:
        if not Path(db_path).exists():
            raise _DatabaseUnavailable() from exc
        raise _DatabaseError(str(exc)) from exc

    try:
        has_schema_version = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if has_schema_version is None:
            conn.close()
            raise _DatabaseUnavailable()
        found_version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    except _DatabaseUnavailable:
        raise
    except Exception as exc:
        conn.close()
        raise _DatabaseError(str(exc)) from exc

    if found_version != SCHEMA_VERSION:
        conn.close()
        raise _DatabaseVersionMismatch(found_version)

    return conn


def _no_scans_body(demo: bool) -> dict:
    return {
        "demo": demo,
        "status": "no_scans_yet",
        "message": "No scans have been recorded yet.",
    }


def _version_mismatch_body(demo: bool, found_version) -> dict:
    return {
        "demo": demo,
        "status": "version_mismatch",
        "message": (
            f"Database schema version mismatch: the database has schema_version={found_version}, "
            f"but this dashboard expects {SCHEMA_VERSION}. Re-initialize or migrate the database."
        ),
    }


def _database_error_body(demo: bool, detail: str) -> dict:
    return {
        "demo": demo,
        "status": "database_error",
        "message": f"Database error: {detail}",
    }


def create_app(demo: bool = False, db_path: Optional[Union[str, Path]] = None) -> Flask:
    """Build the dashboard app.

    `db_path` overrides which database file is opened, for tests that
    point the app at a temporary fixture database; it is looked up
    dynamically from db_path_guard (module-qualified, not a name imported
    directly into this module) so that tests monkeypatching
    db_path_guard.CANONICAL_DB_PATH/DEMO_DB_PATH still take effect even
    without passing db_path explicitly.
    """
    app = Flask(__name__)
    app.config["DEMO_MODE"] = bool(demo)
    if db_path is not None:
        app.config["DB_PATH"] = db_path
    else:
        app.config["DB_PATH"] = db_path_guard.DEMO_DB_PATH if demo else db_path_guard.CANONICAL_DB_PATH

    def _resolve_run_id(conn, requested_run_id):
        if requested_run_id:
            return requested_run_id
        latest = queries.get_latest_complete_run(conn)
        return latest["run_id"] if latest else None

    def _guarded(handler):
        """Open a checked, read-only connection for a route and pass it as
        the handler's first argument; always closes it. If the DB is
        missing/uninitialized or at the wrong schema version, short-circuit
        with a normal 200 JSON body (never a 500) instead of calling the
        handler at all.
        """

        @functools.wraps(handler)
        def wrapper(*args, **kwargs):
            try:
                conn = _open_checked_connection(app.config["DB_PATH"])
            except _DatabaseUnavailable:
                return jsonify(_no_scans_body(app.config["DEMO_MODE"]))
            except _DatabaseVersionMismatch as exc:
                return jsonify(_version_mismatch_body(app.config["DEMO_MODE"], exc.found_version))
            except _DatabaseError as exc:
                return jsonify(_database_error_body(app.config["DEMO_MODE"], exc.detail))
            try:
                return handler(conn, *args, **kwargs)
            finally:
                conn.close()

        return wrapper

    @app.get("/equity")
    def equity_page():
        db_message = None
        try:
            _open_checked_connection(app.config["DB_PATH"]).close()
        except _DatabaseUnavailable:
            db_message = _no_scans_body(app.config["DEMO_MODE"])["message"]
        except _DatabaseVersionMismatch as exc:
            db_message = _version_mismatch_body(app.config["DEMO_MODE"], exc.found_version)["message"]
        except _DatabaseError as exc:
            db_message = _database_error_body(app.config["DEMO_MODE"], exc.detail)["message"]
        return render_template("equity.html", demo=app.config["DEMO_MODE"], db_message=db_message)

    @app.get("/api/equity/summary")
    @_guarded
    def api_summary(conn):
        run = queries.get_latest_complete_run(conn)
        if run is None:
            return jsonify(
                {
                    "demo": app.config["DEMO_MODE"],
                    "run": None,
                    "message": "no COMPLETE scan run yet",
                }
            )
        return jsonify(
            {
                "demo": app.config["DEMO_MODE"],
                "run": queries.summarize_run(run),
                "outdated": queries.is_outdated(run),
            }
        )

    def _e4_context(conn, run_id):
        """The latest COMPLETE E4 scan (if any) and whether its as-of date
        matches this scan run's latest closed session. E4 indicators come
        from a separate acquisition, so a mismatch is surfaced, never hidden."""
        e4 = queries.get_latest_e4_scan(conn)
        if e4 is None:
            return None
        run = queries.get_run(conn, run_id) if run_id else None
        run_session = run.get("latest_closed_session") if run else None
        e4["run_latest_closed_session"] = run_session
        e4["as_of_matches_run"] = bool(run_session) and run_session == e4["asof_date"]
        return e4

    @app.get("/api/equity/candidates")
    @_guarded
    def api_candidates(conn):
        run_id = _resolve_run_id(conn, request.args.get("run_id"))
        page, page_size = _page_params(request.args)
        if run_id is None:
            return jsonify(
                {
                    "demo": app.config["DEMO_MODE"],
                    "run_id": None,
                    "scoring_status": "BLOCKED_B2",
                    "note": "B2 scoring is blocked: this list is unranked.",
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                    "results": [],
                }
            )
        q = request.args.get("q") or None
        status = request.args.get("status") or None
        flag = request.args.get("flag") or None
        try:
            total, rows = queries.get_candidates(conn, run_id, page, page_size, q, status, flag)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        e4 = _e4_context(conn, run_id)
        if e4 is not None:
            features = queries.get_e4_features(conn, e4["scan_id"], [row["symbol"] for row in rows])
            for row in rows:
                row["e4"] = features.get(row["symbol"])
        return jsonify(
            {
                "demo": app.config["DEMO_MODE"],
                "run_id": run_id,
                "scoring_status": "BLOCKED_B2",
                "note": "B2 scoring is blocked: this list is unranked.",
                "e4_scan": e4,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": math.ceil(total / page_size) if page_size else 0,
                "results": rows,
            }
        )

    @app.get("/api/equity/sectors")
    @_guarded
    def api_sectors(conn):
        run_id = _resolve_run_id(conn, request.args.get("run_id"))
        if run_id is None:
            return jsonify({"demo": app.config["DEMO_MODE"], "run_id": None, "sectors": []})
        return jsonify(
            {
                "demo": app.config["DEMO_MODE"],
                "run_id": run_id,
                "sectors": queries.get_sectors(conn, run_id),
            }
        )

    @app.get("/api/equity/stock/<symbol>")
    @_guarded
    def api_stock(conn, symbol):
        run_id = _resolve_run_id(conn, request.args.get("run_id"))
        if run_id is None:
            return jsonify({"error": "no COMPLETE scan run yet"}), 404
        result = queries.get_symbol_result(conn, run_id, symbol)
        if result is None:
            return jsonify({"error": f"{symbol!r} not found in run {run_id!r}"}), 404
        e4 = _e4_context(conn, run_id)
        e4_features = queries.get_e4_features(conn, e4["scan_id"], [symbol]).get(symbol) if e4 else None
        return jsonify(
            {
                "demo": app.config["DEMO_MODE"],
                "run_id": run_id,
                "symbol": symbol,
                "result": result,
                "e4_scan": e4,
                "e4_features": e4_features,
                "candles": queries.get_candles(conn, run_id, symbol),
                "fetch_history": queries.get_fetch_history(conn, symbol),
            }
        )

    @app.get("/api/equity/scan-history")
    @_guarded
    def api_scan_history(conn):
        page, page_size = _page_params(request.args)
        total, rows = queries.get_scan_history(conn, page, page_size)
        now = queries.now_ist_naive()
        runs = []
        for row in rows:
            item = queries.summarize_run(row)
            item["running_stale_warning"] = queries.is_running_stale(row, now)
            runs.append(item)
        return jsonify(
            {
                "demo": app.config["DEMO_MODE"],
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": math.ceil(total / page_size) if page_size else 0,
                "runs": runs,
            }
        )

    return app


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the read-only equity_intel dashboard.")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Serve data/equity_intel_demo.db instead of the real database, with a DEMO banner.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT}; port 5000 is taken by algo_trader's dashboard).",
    )
    return parser


def _port_is_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main() -> None:
    args = _build_arg_parser().parse_args()

    if _port_is_in_use(args.host, args.port):
        print(
            f"Error: port {args.port} is already in use on {args.host}. "
            "Choose a different port with --port (e.g. --port 5051).",
            file=sys.stderr,
        )
        sys.exit(1)

    app = create_app(demo=args.demo)
    url = f"http://{args.host}:{args.port}/equity"
    print(f"Serving equity_intel dashboard at {url}")
    try:
        app.run(host=args.host, port=args.port)
    except OSError as exc:
        # A second, defensive check against a race where something else
        # binds the port between _port_is_in_use()'s probe above and
        # app.run()'s own bind() -- errno differs by platform (EADDRINUSE
        # on POSIX, WSAEADDRINUSE == 10048 on Windows).
        if exc.errno in (errno.EADDRINUSE, 10048):
            print(
                f"Error: port {args.port} is already in use on {args.host}. "
                "Choose a different port with --port (e.g. --port 5051).",
                file=sys.stderr,
            )
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()

"""DDL for data/equity_intel.db, per
docs/architecture/equity_intel_scanner_v1_spec.md.

This replaces the earlier 10-table scaffold's scan_runs and adds
price_fetch_snapshots, symbol_scan_results, and schema_version: that
scaffold predates the frozen V1 spec and modeled a scored/classified/
watchlisted pipeline this package does not implement yet (B2 scoring is
BLOCKED; indicator/feature computation is out of scope for V1 -- see the
spec doc, Sections 1 and 11). Removed outright (not carried forward, not
kept unused): instruments, market_observations, data_quality_results,
feature_sets, component_scores, composite_scores, classification_results,
scan_states -- each is superseded by a V1 table that covers the same
concept (instruments' identity fields and DUMMY*/non-EQ-series data now
live per-run on symbol_scan_results; market_observations/data_quality_results
are superseded by price_fetch_snapshots/symbol_scan_results). paper_watchlist
is kept, unused, per Akshay's explicit instruction (2026-09-27): B2/watchlist
work is deferred, not deleted, and no code in this package writes to it.

No column here has a default value equal to a proposed B2 number,
references an OMS table or broker identifier, or hardcodes a market-data
vendor.

price_fetch_snapshots.scan_run_id and symbol_scan_results.scan_run_id are
foreign keys into scan_runs(run_id): FK enforcement is off by default per
sqlite3 connection and must be turned on with "PRAGMA foreign_keys = ON" on
every connection (equity_intel/persistence/connection.py does this) --
these REFERENCES clauses alone do nothing without that pragma.

This module is executed by equity_intel/tests/test_persistence_schema.py
against an in-memory (":memory:") SQLite connection, to prove the DDL is
syntactically valid SQL, and by equity_intel/persistence/connection.py's
initialize_schema() against the real data/equity_intel.db.
"""
from __future__ import annotations

# SCHEMA_VERSION 2 adds three read-only indexes for the Phase 4 dashboard
# (dashboard/queries.py) -- no column or table shape changed, and no data
# migration is needed: data/equity_intel.db does not exist yet in this
# repo, so there is nothing to migrate. connection.initialize_schema()
# has no upgrade path (a version mismatch on an already-initialized
# database raises SchemaVersionMismatch rather than migrating silently),
# so this bump is safe only because the real database has never been
# created.
SCHEMA_VERSION = 2

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE schema_version (
        version             INTEGER PRIMARY KEY,
        applied_at          TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE scan_runs (
        run_id                  TEXT PRIMARY KEY,
        started_at              TEXT NOT NULL,
        finished_at             TEXT,
        status                  TEXT NOT NULL
                                 CHECK (status IN ('RUNNING', 'COMPLETE', 'ABORTED')),
        abort_reason            TEXT,
        universe_version        TEXT,
        corporate_action_review_version TEXT,
        benchmark               TEXT,
        calendar_source         TEXT,
        calendar_verification   TEXT,
        latest_closed_session   TEXT,
        calendar_dates_json     TEXT,
        price_source            TEXT,
        requested_symbols       INTEGER,
        successful_symbols      INTEGER,
        failed_symbols          INTEGER,
        status_counts_json      TEXT,
        flag_counts_json        TEXT,
        excluded_symbols_json   TEXT,
        errors_json             TEXT,
        git_commit              TEXT,
        git_dirty               INTEGER,
        scoring_status          TEXT NOT NULL CHECK (scoring_status = 'BLOCKED_B2'),
        CHECK (
            status != 'COMPLETE'
            OR (universe_version IS NOT NULL AND corporate_action_review_version IS NOT NULL)
        )
    )
    """,
    # A scan_runs row is never deleted, and once it leaves RUNNING
    # (COMPLETE or ABORTED) it is frozen: no field of a finished run may
    # ever change, including flipping status back to RUNNING. The normal
    # RUNNING -> COMPLETE/ABORTED transition is unaffected: it fires while
    # OLD.status is still 'RUNNING'.
    """
    CREATE TRIGGER prevent_scan_run_delete
    BEFORE DELETE ON scan_runs
    BEGIN
        SELECT RAISE(ABORT, 'scan_runs rows are never deleted');
    END
    """,
    """
    CREATE TRIGGER prevent_finished_scan_run_update
    BEFORE UPDATE ON scan_runs
    WHEN OLD.status != 'RUNNING'
    BEGIN
        SELECT RAISE(ABORT, 'a COMPLETE or ABORTED scan_run can never be updated');
    END
    """,
    # A scan_run must come into existence as RUNNING: COMPLETE/ABORTED are
    # reached only via the normal RUNNING -> COMPLETE/ABORTED UPDATE path,
    # never inserted directly.
    """
    CREATE TRIGGER prevent_scan_run_insert_not_running
    BEFORE INSERT ON scan_runs
    WHEN NEW.status != 'RUNNING'
    BEGIN
        SELECT RAISE(ABORT, 'a scan_run must be created as RUNNING');
    END
    """,
    # Dashboard Overview and Scan History both list/filter scan_runs by
    # status and order by recency (e.g. "the latest COMPLETE run", "all
    # runs newest first") -- run_id (the primary key) is not time-ordered,
    # so without this index those queries would be a full table scan.
    """
    CREATE INDEX idx_scan_runs_status_started_at ON scan_runs (status, started_at)
    """,
    """
    CREATE TABLE price_fetch_snapshots (
        scan_run_id              TEXT NOT NULL REFERENCES scan_runs(run_id),
        symbol                   TEXT NOT NULL,
        trading_date             TEXT NOT NULL,
        source                   TEXT NOT NULL,
        fetched_at_ist           TEXT NOT NULL,
        open                     TEXT,
        high                     TEXT,
        low                      TEXT,
        close                    TEXT,
        volume                   INTEGER,
        content_hash             TEXT NOT NULL,
        candle_validation_status TEXT NOT NULL CHECK (candle_validation_status IN ('VALID', 'INVALID')),
        validation_errors_json   TEXT,
        source_metadata_json     TEXT,
        PRIMARY KEY (scan_run_id, symbol, trading_date, source)
    )
    """,
    # Immutability enforced at the DB level, not just by application code
    # never issuing an UPDATE/DELETE: see docs/architecture/
    # equity_intel_scanner_v1_spec.md Section 8 ("never updated or deleted").
    """
    CREATE TRIGGER prevent_price_fetch_snapshot_update
    BEFORE UPDATE ON price_fetch_snapshots
    BEGIN
        SELECT RAISE(ABORT, 'price_fetch_snapshots is append-only: UPDATE is forbidden');
    END
    """,
    """
    CREATE TRIGGER prevent_price_fetch_snapshot_delete
    BEFORE DELETE ON price_fetch_snapshots
    BEGIN
        SELECT RAISE(ABORT, 'price_fetch_snapshots is append-only: DELETE is forbidden');
    END
    """,
    # A price_fetch_snapshot may only be inserted while its owning scan_run
    # is still RUNNING: once that run is COMPLETE or ABORTED, no further
    # snapshots may be appended to it either.
    """
    CREATE TRIGGER prevent_price_fetch_snapshot_insert_for_finished_run
    BEFORE INSERT ON price_fetch_snapshots
    WHEN (SELECT status FROM scan_runs WHERE run_id = NEW.scan_run_id) != 'RUNNING'
    BEGIN
        SELECT RAISE(ABORT, 'price_fetch_snapshots may only be written while the owning scan_run is RUNNING');
    END
    """,
    # The Stock Details page's "fetch history across runs" for one symbol
    # is not scoped to a single scan_run_id (the table's primary key
    # prefix), so it needs its own index to avoid a full table scan.
    """
    CREATE INDEX idx_price_fetch_snapshots_symbol ON price_fetch_snapshots (symbol, trading_date)
    """,
    """
    CREATE TABLE symbol_scan_results (
        scan_run_id                     TEXT NOT NULL REFERENCES scan_runs(run_id),
        symbol                          TEXT NOT NULL,
        instrument_key                  TEXT,
        isin                            TEXT,
        series                          TEXT,
        company_name                    TEXT,
        sector                          TEXT,
        symbol_data_status              TEXT NOT NULL
                                         CHECK (symbol_data_status IN
                                             ('VALID', 'INSUFFICIENT_HISTORY', 'STALE', 'FAILED')),
        status_reason                   TEXT,
        available_session_count         INTEGER,
        missing_session_count           INTEGER,
        history_gaps_flag               INTEGER NOT NULL DEFAULT 0,
        corporate_action_review_flag    INTEGER NOT NULL DEFAULT 0,
        price_break_detected_flag       INTEGER NOT NULL DEFAULT 0,
        non_eq_series_flag              INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (scan_run_id, symbol)
    )
    """,
    # A symbol_scan_result may only be written (inserted, updated, or
    # deleted) while its owning scan_run is still RUNNING: once that run is
    # COMPLETE or ABORTED, every one of its symbol results is frozen too.
    """
    CREATE TRIGGER prevent_symbol_scan_result_insert_for_finished_run
    BEFORE INSERT ON symbol_scan_results
    WHEN (SELECT status FROM scan_runs WHERE run_id = NEW.scan_run_id) != 'RUNNING'
    BEGIN
        SELECT RAISE(ABORT, 'symbol_scan_results may only be written while the owning scan_run is RUNNING');
    END
    """,
    """
    CREATE TRIGGER prevent_symbol_scan_result_update_for_finished_run
    BEFORE UPDATE ON symbol_scan_results
    WHEN (SELECT status FROM scan_runs WHERE run_id = OLD.scan_run_id) != 'RUNNING'
    BEGIN
        SELECT RAISE(ABORT, 'symbol_scan_results may only be modified while the owning scan_run is RUNNING');
    END
    """,
    """
    CREATE TRIGGER prevent_symbol_scan_result_delete_for_finished_run
    BEFORE DELETE ON symbol_scan_results
    WHEN (SELECT status FROM scan_runs WHERE run_id = OLD.scan_run_id) != 'RUNNING'
    BEGIN
        SELECT RAISE(ABORT, 'symbol_scan_results may only be deleted while the owning scan_run is RUNNING');
    END
    """,
    # The Stock Explorer page filters one run's symbol_scan_results by
    # symbol_data_status (e.g. "show only FAILED"); scan_run_id alone is
    # already the primary-key prefix, so this index adds just the status
    # column needed to avoid scanning every row of a run to apply the filter.
    """
    CREATE INDEX idx_symbol_scan_results_run_status
        ON symbol_scan_results (scan_run_id, symbol_data_status)
    """,
    # Unused in V1 (no code writes to this table): kept, not deleted, per
    # Akshay's explicit instruction (2026-09-27) -- B2/watchlist work is
    # deferred, not removed from the schema. Columns unchanged from the
    # pre-V1 scaffold.
    """
    CREATE TABLE paper_watchlist (
        scan_id             TEXT NOT NULL,
        instrument_id       TEXT NOT NULL,
        rank                INTEGER,
        composite            INTEGER,
        score_version        TEXT,
        PRIMARY KEY (scan_id, instrument_id)
    )
    """,
)

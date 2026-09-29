"""Schema parsing/validation -- against an in-memory SQLite connection.

This test NEVER opens data/equity_intel.db or any path on disk. ":memory:"
creates a transient, process-local database that is discarded when the
connection closes; it is not the file this scaffold is forbidden from
creating.
"""
import sqlite3

from equity_intel.persistence.schema import SCHEMA_STATEMENTS


def test_schema_statements_are_valid_sql_against_an_in_memory_database():
    conn = sqlite3.connect(":memory:")
    try:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def test_schema_has_no_hardcoded_candidate_cutoff_or_watchlist_k_value():
    joined = "\n".join(SCHEMA_STATEMENTS)
    assert "70" not in joined
    assert "DEFAULT 10" not in joined
    assert "WATCHLIST_K" not in joined


def test_schema_has_no_broker_or_options_order_columns():
    joined = "\n".join(SCHEMA_STATEMENTS).lower()
    for forbidden in ("broker_id", "order_id", "strike", "option_type", "lot_size", "position_id"):
        assert forbidden not in joined


def test_schema_tables_cover_the_required_persisted_concepts():
    # Per docs/architecture/equity_intel_scanner_v1_spec.md (Sections 8-9,
    # 11): V1 is data-only (no scoring/classification/candidate/watchlist
    # tables of its own) and tracks schema_version explicitly since
    # data/equity_intel.db does not exist yet and this is a from-scratch
    # schema, not a migration. paper_watchlist is kept (unused by V1 code)
    # per Akshay's explicit instruction -- deferred, not deleted.
    joined = "\n".join(SCHEMA_STATEMENTS)
    for table in (
        "schema_version",
        "scan_runs",
        "price_fetch_snapshots",
        "symbol_scan_results",
        "paper_watchlist",
    ):
        assert f"CREATE TABLE {table}" in joined, table


def test_scan_runs_records_provenance_hashes_for_both_reference_csvs():
    # Per docs/architecture/equity_intel_scanner_v1_spec.md, Sections 2 and
    # 7: universe_version and corporate_action_review_version get the same
    # SHA-256-of-the-CSV-file treatment.
    conn = sqlite3.connect(":memory:")
    try:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        conn.execute("PRAGMA table_info(scan_runs)")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(scan_runs)").fetchall()}
        assert "universe_version" in columns
        assert "corporate_action_review_version" in columns
    finally:
        conn.close()

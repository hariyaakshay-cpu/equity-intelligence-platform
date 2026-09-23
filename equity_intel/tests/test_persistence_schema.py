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
    joined = "\n".join(SCHEMA_STATEMENTS)
    for table in (
        "instruments",
        "scan_runs",
        "market_observations",
        "data_quality_results",
        "feature_sets",
        "component_scores",
        "composite_scores",
        "classification_results",
        "scan_states",
        "paper_watchlist",
    ):
        assert f"CREATE TABLE {table}" in joined, table

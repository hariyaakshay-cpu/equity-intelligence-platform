"""Neutral DDL for future scoring-era Equity Intelligence tables.

Every table below stores the RESULT of a decision (a score, a status, a
classification, a state), never the RULE that produces it. No column has a
default value equal to a proposed B2 number (70, 10, or any band point
value). No column references an OMS table, a broker identifier, or an
options-order field. No column hardcodes a market-data vendor.

The E1-E3 acquisition tables are defined and created by
``equity_intel.persistence.connection``. These existing scoring-era tables
remain inert; no scores, classifications, states, or watchlists are written.
"""
from __future__ import annotations

# This legacy neutral schema contains no vendor-specific defaults.

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE instruments (
        instrument_id       TEXT PRIMARY KEY,
        symbol              TEXT NOT NULL,
        exchange_symbol     TEXT,
        secondary_vendor_ticker TEXT,
        instrument_key      TEXT,
        isin                TEXT,
        company_name        TEXT,
        sector              TEXT,
        active              INTEGER
    )
    """,
    """
    CREATE TABLE scan_runs (
        scan_id             TEXT PRIMARY KEY,
        asof_date           TEXT,
        expected_asof_date  TEXT,
        score_version       TEXT,
        status              TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE market_observations (
        instrument_id       TEXT NOT NULL,
        observation_date    TEXT NOT NULL,
        high                REAL,
        low                 REAL,
        close               REAL,
        volume              REAL,
        PRIMARY KEY (instrument_id, observation_date)
    )
    """,
    """
    CREATE TABLE data_quality_results (
        scan_id             TEXT NOT NULL,
        instrument_id       TEXT NOT NULL,
        status              TEXT NOT NULL,
        reason              TEXT,
        n_bars              INTEGER,
        w52_complete        INTEGER,
        PRIMARY KEY (scan_id, instrument_id)
    )
    """,
    """
    CREATE TABLE feature_sets (
        scan_id             TEXT NOT NULL,
        instrument_id       TEXT NOT NULL,
        ema_short           REAL,
        ema_medium          REAL,
        ema_long            REAL,
        ema_medium_lag      REAL,
        rsi                 REAL,
        roc                 REAL,
        relative_return     REAL,
        relative_volume     REAL,
        distance_from_high  REAL,
        prior_high_short    REAL,
        prior_high_long     REAL,
        atr_percent         REAL,
        PRIMARY KEY (scan_id, instrument_id)
    )
    """,
    """
    CREATE TABLE component_scores (
        scan_id             TEXT NOT NULL,
        instrument_id       TEXT NOT NULL,
        component_name      TEXT NOT NULL,
        score                INTEGER,
        basis               TEXT,
        PRIMARY KEY (scan_id, instrument_id, component_name)
    )
    """,
    """
    CREATE TABLE composite_scores (
        scan_id             TEXT NOT NULL,
        instrument_id       TEXT NOT NULL,
        composite            INTEGER,
        PRIMARY KEY (scan_id, instrument_id)
    )
    """,
    """
    CREATE TABLE classification_results (
        scan_id             TEXT NOT NULL,
        instrument_id       TEXT NOT NULL,
        tags                TEXT,
        primary_tag          TEXT,
        PRIMARY KEY (scan_id, instrument_id)
    )
    """,
    """
    CREATE TABLE scan_states (
        scan_id             TEXT NOT NULL,
        instrument_id       TEXT NOT NULL,
        state               TEXT NOT NULL,
        rank                INTEGER,
        PRIMARY KEY (scan_id, instrument_id)
    )
    """,
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

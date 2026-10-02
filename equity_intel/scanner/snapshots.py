"""Canonical price quantization, content-hash, and append-only snapshot writing.

Per docs/architecture/equity_intel_scanner_v1_spec.md Section 8:

- Canonical hash: SHA-256 of "YYYY-MM-DD|open|high|low|close|volume";
  prices as Decimal quantized to 2dp with ROUND_HALF_UP; volume as
  integer; null represented as empty string.
- Stored form matches the hash input exactly: open/high/low/close are
  persisted as TEXT holding the same 2dp-quantized decimal string used to
  build content_hash -- never a REAL/float column. E.g. 100.5 is
  quantized and stored as the string "100.50", and that exact string is
  what content_hash's input string is built from.
"""
from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence, Union

TWO_PLACES = Decimal("0.01")

Number = Union[int, float, str, Decimal]


def quantize_price(value: Optional[Number]) -> Optional[Decimal]:
    """2dp, ROUND_HALF_UP. None passes through as None -- a missing price
    is never coerced to 0 or any other sentinel (Section 8 represents it
    as an empty string in the hash input, and a NULL column). Goes
    through str(value) first, never Decimal(value) directly on a float,
    to avoid binary-float representation noise (e.g. Decimal(100.1) !=
    Decimal("100.1"))."""
    if value is None:
        return None
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def price_to_text(value: Optional[Number]) -> Optional[str]:
    """The exact TEXT column value: the 2dp-quantized decimal string, or
    None (NULL) -- never a REAL/float."""
    quantized = quantize_price(value)
    return str(quantized) if quantized is not None else None


def _hash_field(value: Optional[Number]) -> str:
    quantized = quantize_price(value)
    return str(quantized) if quantized is not None else ""


def compute_content_hash(
    trading_date: str,
    open_: Optional[Number],
    high: Optional[Number],
    low: Optional[Number],
    close: Optional[Number],
    volume: Optional[int],
) -> str:
    """SHA-256 of "YYYY-MM-DD|open|high|low|close|volume" -- prices 2dp
    quantized (ROUND_HALF_UP), volume as integer text, null as ''."""
    volume_text = "" if volume is None else str(int(volume))
    payload = "|".join(
        [
            trading_date,
            _hash_field(open_),
            _hash_field(high),
            _hash_field(low),
            _hash_field(close),
            volume_text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_content_hash_from_stored_row(row: Dict) -> str:
    """Recompute content_hash directly from an already-stored
    price_fetch_snapshots row -- its TEXT open/high/low/close columns
    (already 2dp-quantized decimal strings, or None) and integer volume
    column -- without re-quantizing. Proves Section 8's "stored form
    matches the hash input exactly" property: this must equal the
    content_hash that was written.
    """
    volume = row.get("volume")
    volume_text = "" if volume is None else str(int(volume))
    payload = "|".join(
        [
            row["trading_date"],
            row.get("open") or "",
            row.get("high") or "",
            row.get("low") or "",
            row.get("close") or "",
            volume_text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_snapshot(
    conn,
    *,
    scan_run_id: str,
    symbol: str,
    trading_date: str,
    source: str,
    fetched_at_ist: str,
    open_: Optional[Number],
    high: Optional[Number],
    low: Optional[Number],
    close: Optional[Number],
    volume: Optional[int],
    candle_validation_status: str,
    validation_errors: Optional[Sequence[str]] = None,
    source_metadata: Optional[Dict] = None,
) -> str:
    """Insert one append-only PriceFetchSnapshot row. Never an UPDATE --
    schema.py's prevent_price_fetch_snapshot_update/delete triggers would
    refuse one anyway (Section 8), and the (scan_run_id, symbol,
    trading_date, source) primary key refuses a duplicate insert within
    the same run outright (also Section 8: "retries inside the same run
    must not duplicate").

    Returns the content_hash that was written.
    """
    content_hash = compute_content_hash(trading_date, open_, high, low, close, volume)
    conn.execute(
        """
        INSERT INTO price_fetch_snapshots
            (scan_run_id, symbol, trading_date, source, fetched_at_ist,
             open, high, low, close, volume, content_hash,
             candle_validation_status, validation_errors_json, source_metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_run_id,
            symbol,
            trading_date,
            source,
            fetched_at_ist,
            price_to_text(open_),
            price_to_text(high),
            price_to_text(low),
            price_to_text(close),
            None if volume is None else int(volume),
            content_hash,
            candle_validation_status,
            json.dumps(list(validation_errors)) if validation_errors else None,
            json.dumps(source_metadata) if source_metadata else None,
        ),
    )
    return content_hash

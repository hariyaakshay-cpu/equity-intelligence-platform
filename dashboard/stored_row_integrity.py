"""Stored-row integrity: do stored price_fetch_snapshots rows still reproduce their stored content_hash?

Shared by the dashboard pages that show it for ONE symbol. It hashes only text already stored in the
rows it is given (no vendor call, no price maths), so it can only say that a stored row matches its
stored hash. It does not prove the vendor data is unchanged. Like queries.py it never imports sqlite3.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from equity_intel.scanner.snapshots import compute_content_hash_from_stored_row

LABEL = "stored-row integrity"


def check_rows(rows: Sequence[dict], recompute: Optional[Callable[[dict], str]] = None) -> dict:
    """MATCH, MISMATCH or UNAVAILABLE for `rows` (dicts with trading_date, open, high, low, close,
    volume and content_hash, one symbol's stored bars).

    UNAVAILABLE means there are no rows to check; it is never reported as MATCH. `mismatched` lists the
    trading dates whose recomputed hash differs from the stored one. `recompute` defaults to the canonical
    compute_content_hash_from_stored_row; a caller may pass its own (the Stock Detail page passes its
    module-level name so that tests can substitute it).
    """
    recompute = recompute or compute_content_hash_from_stored_row
    mismatched = [r["trading_date"] for r in rows if recompute(r) != r["content_hash"]]
    state = "UNAVAILABLE" if not rows else ("MISMATCH" if mismatched else "MATCH")
    return {"label": LABEL, "state": state, "bars": len(rows), "mismatched": mismatched}

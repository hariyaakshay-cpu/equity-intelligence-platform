"""The scanner's own connection entrypoint -- canonical database only.

db_path_guard.assert_allowed_db_path accepts two paths now: the canonical
database and DEMO_DB_PATH (added in Phase 4, for the read-only dashboard's
--demo mode -- see equity_intel/persistence/db_path_guard.py). That guard
is deliberately permissive for read-only dashboard use, but the scanner is
a writer: it must never write a real scan into data/equity_intel_demo.db,
and never write fabricated data into data/equity_intel.db. This module is
the scanner-side allow-list, narrower than db_path_guard's: it accepts
only the canonical path, the mirror image of
scripts/dashboard_demo_seed.py's seed_demo_database(), which accepts only
DEMO_DB_PATH.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from equity_intel.persistence import connection, db_path_guard


class RefusedNonCanonicalDatabaseError(RuntimeError):
    """Raised when the scanner is asked to write anywhere but the one
    canonical database."""


def get_scan_connection(path: Optional[Union[str, Path]] = None):
    """Open a writable connection to the canonical database only.

    `path` defaults to db_path_guard.CANONICAL_DB_PATH, looked up
    dynamically (module-qualified, not imported directly into this
    module) so that tests monkeypatching db_path_guard.CANONICAL_DB_PATH
    still take effect. Does not initialize the schema -- call
    equity_intel.persistence.connection.initialize_schema() on the
    returned connection if needed, same as connection.get_connection().

    Raises:
        RefusedNonCanonicalDatabaseError: if `path` does not resolve to
            the canonical database (this includes DEMO_DB_PATH, and any
            other path db_path_guard itself would have allowed or
            refused). Checked before any file is touched.
    """
    if path is None:
        path = db_path_guard.CANONICAL_DB_PATH
    resolved = Path(path).resolve(strict=False)
    canonical = db_path_guard.CANONICAL_DB_PATH.resolve(strict=False)
    if resolved != canonical:
        raise RefusedNonCanonicalDatabaseError(
            f"the scanner only ever writes to the canonical database ({canonical}); "
            f"refusing to write to {resolved}"
        )
    return connection.get_connection(resolved)

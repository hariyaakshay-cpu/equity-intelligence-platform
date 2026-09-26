"""Allow-list guard for equity_intel's single future database connection.

The frozen architecture names exactly one on-disk database for this
package: <repo_root>/data/equity_intel.db (CANONICAL_DB_PATH below). This
module accepts only that one resolved path and refuses everything else --
including in-process SQLite shorthand (":memory:") and URI shorthand
("file:...") that could otherwise bypass a naive filename-only check
entirely, since neither of those is a real on-disk file path at all.

There is no filename-only rule (a same-named file in the wrong directory
is refused) and no tmp_path special case in this module: a test that needs
a temporary canonical path monkeypatches CANONICAL_DB_PATH itself rather
than this module accepting a second, looser rule. See
equity_intel/tests/test_db_connection_boundary.py for the static test
proving no other module ever opens a real connection, and
docs/architecture/equity_intel_boundary_decision.md for the decision
record.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_DB_PATH = REPO_ROOT / "data" / "equity_intel.db"


def assert_allowed_db_path(path: str | Path) -> Path:
    """Return the resolved path if it is the one canonical database path.

    Raises:
        ValueError: if `path` is in-process/URI SQLite shorthand (a string
            starting with ":" or "file:"), or resolves to anything other
            than the current value of CANONICAL_DB_PATH.
    """
    if isinstance(path, str) and (path.startswith(":") or path.startswith("file:")):
        raise ValueError(
            f"Refusing in-process/URI SQLite target, not a real file path: {path!r}"
        )

    resolved = Path(path).resolve(strict=False)
    canonical = CANONICAL_DB_PATH.resolve(strict=False)
    if resolved != canonical:
        raise ValueError(f"Refusing to open forbidden database path: {resolved}")
    return resolved

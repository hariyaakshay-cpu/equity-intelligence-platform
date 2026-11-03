"""12-1 momentum signals view (read-only). Reads the newest data/signals/momentum_12_1_<asof>.json written by
scripts/equity_momentum_signals.py. Never writes; no database access. No target, no stop-loss."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

BANNER = "12-1 momentum - NOT VALIDATED (failed DEV test narrowly, 3 Nov 2026) - research only - not trade advice"
STALE_DAYS = 4


def build(signals_dir: Path, today: Optional[date] = None) -> dict:
    files = sorted(Path(signals_dir).glob("momentum_12_1_*.json")) if Path(signals_dir).is_dir() else []
    if not files:
        return {"available": False,
                "message": "No momentum list yet. Run scripts/equity_momentum_signals.py (see its docstring)."}
    body = json.loads(files[-1].read_text())
    today = today or date.today()
    age = (today - date.fromisoformat(body["asof"])).days
    return {"available": True, "file": files[-1].name, "age_days": age, "stale": age > STALE_DAYS, **body}

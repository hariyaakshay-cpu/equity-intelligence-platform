"""Live intraday PAPER board view (read-only). Reads the newest data/paper_board/<YYYY-MM-DD>.json
written by scripts/equity_paper_board.py. PAPER ONLY - NOT VALIDATED - no orders."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from equity_intel.config import IST

BANNER = "PAPER ONLY - NOT VALIDATED - the order-win fade failed its test; this tracks it live - no orders"
LIVE_MINUTES = 12            # the runner writes every 5 minutes in market hours
_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def build(board_dir: Path, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(IST)
    files = sorted(p for p in Path(board_dir).glob("*.json") if _NAME.match(p.name)) if Path(board_dir).is_dir() else []
    if not files:
        return {"available": False, "message": "The paper board has not run yet. It starts on market days at 08:40."}
    path = files[-1]
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"available": False, "message": f"Could not read {path.name}: {type(exc).__name__}"}
    is_today = st.get("date") == now.date().isoformat()
    live = False
    if is_today and st.get("updated"):
        try:
            upd = datetime.combine(now.date(), datetime.strptime(st["updated"], "%H:%M:%S").time(), IST)
            live = (now - upd).total_seconds() <= LIVE_MINUTES * 60 and now.time() < datetime.strptime("15:40", "%H:%M").time()
        except ValueError:
            live = False
    return {"available": True, "is_today": is_today, "live": live, **st}

"""PROVISIONAL v0: send the daily watchlist to Telegram.

Default is a DRY RUN that only prints the message. Pass --send to actually
send (needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import signals
from equity_intel.alerts import telegram_v0
from equity_intel.persistence.connection import get_read_only_connection
from equity_intel.scanner.execution_guard import assert_no_forbidden_modules_loaded


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="actually send (default: dry run, print only)")
    args = parser.parse_args(argv)
    assert_no_forbidden_modules_loaded()
    conn = get_read_only_connection(ROOT / "data/equity_intel.db")
    try:
        message = telegram_v0.format_message(signals.build(conn))
    finally:
        conn.close()
    print(message)
    if not args.send:
        print("\n[dry run: nothing sent; pass --send to send]")
        return 0
    print(telegram_v0.send(message).get("ok"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

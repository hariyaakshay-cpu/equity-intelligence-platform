"""Print the daily scanner digest; send it to Telegram only with --send."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from equity_intel.persistence import connection, db_path_guard
from telegram_bot import digest, sender


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="actually send (default: dry run, print only)")
    parser.add_argument("--db", default=str(db_path_guard.CANONICAL_DB_PATH))
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")
    try:
        conn = connection.get_read_only_connection(args.db)
    except Exception as exc:
        print(f"Cannot open database {args.db}: {exc}", file=sys.stderr)
        return 1
    try:
        text = digest.build_digest(conn)
    finally:
        conn.close()

    print(text)
    if not args.send:
        print("\n[dry run: nothing sent; pass --send to deliver]")
        return 0
    token, chat_id = sender.load_credentials()
    sender.send_message(text, token, chat_id)
    print("\n[sent]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

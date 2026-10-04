"""Daily refresh: scan -> E4 acquisition -> E4 scan -> Telegram digest.

Runs each existing script as a subprocess, in order, and stops at the first
failure. On failure it sends a short Telegram alert instead of the digest,
so a dead Upstox token never produces a digest that looks fresh. Skips
weekends and NSE holidays. Dry run unless --send is given.

    python scripts/daily_refresh.py --send --only-on-session
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STEP_TIMEOUT_SECONDS = 60 * 60
STEPS = (
    ("scanner run", ["scripts/equity_scan.py"]),
    ("E4 data acquisition", ["scripts/equity_data_acquisition.py"]),
    ("E4 indicator scan", ["scripts/equity_e4_scan.py"]),
)
ALERT_HINT = "If this is an auth failure, refresh the token: python scripts/upstox_auth.py"


def run_pipeline(steps=STEPS, run=subprocess.run, python=sys.executable, cwd=ROOT):
    """Returns (ok, failed_step_name_or_None, detail). Stops at first failure."""
    for name, argv in steps:
        try:
            result = run([python, *argv], cwd=cwd, timeout=STEP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return False, name, f"timed out after {STEP_TIMEOUT_SECONDS // 60} min"
        if result.returncode != 0:
            return False, name, f"exit code {result.returncode}"
    return True, None, ""


def alert_text(step: str, detail: str) -> str:
    return f"Equity data refresh FAILED at: {step} ({detail}).\nNo digest sent. {ALERT_HINT}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="send the digest/alert (default: dry run)")
    parser.add_argument("--only-on-session", action="store_true")
    args = parser.parse_args(argv)

    from dashboard.queries import now_ist_naive
    from telegram_bot import schedule

    stamp = now_ist_naive()
    print(f"[{stamp:%Y-%m-%d %H:%M}] daily refresh start")
    if args.only_on_session:
        is_session, basis = schedule.is_session_day(stamp.date())
        if not is_session:
            print(f"{stamp.date()} is not an NSE session day ({basis}); nothing to do.")
            return 0

    ok, step, detail = run_pipeline()
    if not ok:
        text = alert_text(step, detail)
        print(text, file=sys.stderr)
        if args.send:
            from dotenv import load_dotenv
            from telegram_bot import sender
            load_dotenv(ROOT / ".env")
            try:
                sender.send_message(text, *sender.load_credentials())
            except (sender.TelegramConfigError, sender.TelegramSendError) as exc:
                print(f"alert not delivered: {exc}", file=sys.stderr)
        return 1

    digest_argv = [sys.executable, "scripts/telegram_digest.py"] + (["--send"] if args.send else [])
    return subprocess.run(digest_argv, cwd=ROOT, timeout=STEP_TIMEOUT_SECONDS).returncode


if __name__ == "__main__":
    raise SystemExit(main())

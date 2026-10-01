"""
Daily Upstox login helper.

    python -m jobs.upstox_auth            # print login URL, paste redirect URL/code, save token
    python -m jobs.upstox_auth --status   # show whether a valid token is cached

Requires UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET and UPSTOX_REDIRECT_URI in .env
(the redirect URI must match the one registered on your Upstox app).
"""

import argparse
import secrets
import sys
from typing import Optional

from config import Settings
from services.upstox import auth


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(description="Upstox OAuth login")
    p.add_argument("--status", action="store_true", help="Show cached token status")
    args = p.parse_args(argv)
    s = Settings()

    if args.status:
        token = auth.load_token()
        print("Valid token cached" if token else "No valid token; run login")
        return 0 if token else 1

    if not (s.UPSTOX_CLIENT_ID and s.UPSTOX_CLIENT_SECRET and s.UPSTOX_REDIRECT_URI):
        print("Set UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI in .env", file=sys.stderr)
        return 2

    state = secrets.token_urlsafe(8)
    print("1. Open this URL and log in:\n")
    print(auth.build_login_url(s.UPSTOX_CLIENT_ID, s.UPSTOX_REDIRECT_URI, s.UPSTOX_BASE_URL, state))
    print("\n2. Paste the full URL you were redirected to (or just the code):")
    code = auth.extract_code(input("> "))
    token = auth.exchange_code(
        code, s.UPSTOX_CLIENT_ID, s.UPSTOX_CLIENT_SECRET, s.UPSTOX_REDIRECT_URI, s.UPSTOX_BASE_URL
    )
    expires = auth.save_token(token)
    print(f"Token saved to {auth.TOKEN_FILE}, valid until {expires:%Y-%m-%d %H:%M} IST")
    return 0


if __name__ == "__main__":
    sys.exit(main())

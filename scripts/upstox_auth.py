"""Refresh the Upstox access token and store it in this repo's .env.

Run:  python scripts/upstox_auth.py

Upstox tokens expire daily (~03:30 IST). This opens the login page, asks for
the `code` from the redirect URL, exchanges it, and writes UPSTOX_ACCESS_TOKEN
into .env. API key/secret/redirect URI are read from this repo's .env, or from
the legacy algo_trader .env if absent here. Secrets are never printed.
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
LEGACY_ENV_PATH = Path.home() / "algo_trader" / ".env"
AUTH_DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
REQUIRED = ("UPSTOX_API_KEY", "UPSTOX_API_SECRET", "UPSTOX_REDIRECT_URI")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    config = {**read_env(LEGACY_ENV_PATH), **read_env(ENV_PATH)}
    missing = [name for name in REQUIRED if not config.get(name)]
    if missing:
        print(f"Missing {', '.join(missing)} in {ENV_PATH} (or {LEGACY_ENV_PATH}).")
        return 1

    login_url = f"{AUTH_DIALOG_URL}?" + urlencode({
        "response_type": "code",
        "client_id": config["UPSTOX_API_KEY"],
        "redirect_uri": config["UPSTOX_REDIRECT_URI"],
    })
    print("Log in to Upstox and approve access:\n\n  " + login_url + "\n")
    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    pasted = input("Paste the full redirect URL (or just the code): ").strip()
    code = parse_qs(urlparse(pasted).query).get("code", [pasted])[0] if pasted else ""
    if not code:
        print("No code provided.")
        return 1

    response = requests.post(TOKEN_URL, headers={"Accept": "application/json"}, timeout=15, data={
        "code": code,
        "client_id": config["UPSTOX_API_KEY"],
        "client_secret": config["UPSTOX_API_SECRET"],
        "redirect_uri": config["UPSTOX_REDIRECT_URI"],
        "grant_type": "authorization_code",
    })
    token = response.json().get("access_token") if response.status_code == 200 else None
    if not token:
        print(f"Token exchange failed (HTTP {response.status_code}): {response.text}")
        return 1

    write_env_value(ENV_PATH, "UPSTOX_ACCESS_TOKEN", token)
    print(f"Access token saved to {ENV_PATH}. Valid until ~03:30 IST.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

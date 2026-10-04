"""Send a plain-text message through the Telegram Bot API.

The token is read from the environment and is never logged or included in
exceptions. Plain text only (no parse_mode), so no escaping pitfalls.
"""
from __future__ import annotations

import os

import requests

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SECONDS = 15


class TelegramConfigError(RuntimeError):
    pass


class TelegramSendError(RuntimeError):
    pass


def load_credentials(env=None) -> tuple[str, str]:
    env = os.environ if env is None else env
    token, chat_id = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise TelegramConfigError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set")
    return token, chat_id


def send_message(text: str, token: str, chat_id: str, post=requests.post) -> None:
    try:
        response = post(
            API_URL.format(token=token),
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise TelegramSendError(f"request failed: {type(exc).__name__}") from None
    if response.status_code != 200:
        raise TelegramSendError(f"Telegram API returned HTTP {response.status_code}")

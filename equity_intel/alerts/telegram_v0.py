"""PROVISIONAL v0 Telegram message for the daily watchlist.

format_message() is pure. send() is the only function that touches the network
and it needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment; the
token is never logged or stored. This module sends text only: no orders, no
broker or engine imports. The owner places any trades himself.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Optional

TELEGRAM_LIMIT = 4096


def format_message(body: dict, max_rows: Optional[int] = None) -> str:
    notice = "PROVISIONAL v0 - not B2-authoritative, untested for expectancy, not trade advice."
    if not body.get("available"):
        return f"Equity daily watchlist\n{notice}\n{body.get('message', 'No provisional scores yet.')}"
    meta = body["meta"]
    rows = [c for c in body["candidates"] if c.get("watchlist")]
    if max_rows is not None:
        rows = rows[:max_rows]
    lines = [f"Equity daily watchlist - data as of {meta['asof_date']} (end of day)", notice]
    if body.get("outdated"):
        lines.append(f"WARNING: outdated, latest expected session is {body['expected_latest_session']}.")
    lines.append(f"{body['counts']['candidates']} candidate(s) at composite >= {meta['candidate_cutoff']}; top {meta['watchlist_limit']} shown.")
    if not rows:
        lines.append("No stock reaches the provisional cutoff.")
    for c in rows:
        close = "n/a" if c.get("close") is None else f"{c['close']:.2f}"
        lines.append(f"{c['rank']}. {c['symbol']} score {c['composite']} "
                     f"(T{c['trend']} M{c['momentum']} R{c['relative_strength']} V{c['volume']} S{c['structure']}) close {close}")
    for key, title in (("short", "SHORT TERM (momentum + volume + breakout)"),
                       ("medium", "MEDIUM TERM (trend + relative strength + 52w distance)")):
        picks = [c for c in (body.get("horizons") or {}).get(key, []) if c.get("watchlist")]
        if max_rows is not None:
            picks = picks[:max_rows]
        lines.append(f"{title} - score % of its own max:")
        lines.extend(f"{c['rank']}. {c['symbol']} {c['score']}%" for c in picks) if picks else lines.append("none above the cutoff")
    lines.append("Daily signals only. Intraday signals are not built yet.")
    text = "\n".join(lines)
    return text if len(text) <= TELEGRAM_LIMIT else text[: TELEGRAM_LIMIT - 20] + "\n...(truncated)"


def send(text: str, *, token: Optional[str] = None, chat_id: Optional[str] = None, timeout: int = 20) -> dict:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment to send.")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode())

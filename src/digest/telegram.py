"""Telegram Bot API helpers (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send a plain-text message to a Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Telegram sendMessage failed ({exc.code}): {detail}") from exc

    if not body.get("ok"):
        raise RuntimeError(f"Telegram sendMessage rejected: {body!r}")

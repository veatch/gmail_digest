"""Telegram Bot API helpers (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def send_message(
    bot_token: str, chat_id: str, text: str, parse_mode: str | None = None
) -> None:
    """Send a message to a Telegram chat, optionally using its HTML parser."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    fields = {"chat_id": chat_id, "text": text}
    if parse_mode:
        fields["parse_mode"] = parse_mode
    payload = urllib.parse.urlencode(fields).encode()
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


def get_updates(bot_token: str, offset: int) -> list[dict[str, object]]:
    """Fetch pending text-message updates starting at the persisted offset."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?"
    query = urllib.parse.urlencode(
        {
            "offset": offset,
            "limit": 10,
            "timeout": 0,
            "allowed_updates": json.dumps(["message"]),
        }
    )
    request = urllib.request.Request(url + query, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Telegram getUpdates failed ({exc.code}): {detail}") from exc

    if not body.get("ok"):
        raise RuntimeError(f"Telegram getUpdates rejected: {body!r}")
    result = body.get("result")
    if not isinstance(result, list):
        raise RuntimeError(f"Telegram getUpdates returned invalid result: {body!r}")
    return [update for update in result if isinstance(update, dict)]

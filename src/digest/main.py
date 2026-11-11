"""Send one Telegram header list for each sender with new newsletter mail."""

from __future__ import annotations

import os
import sys

from digest.config import find_config_path, load_config
from digest.mail import apply_processed_label, fetch_unprocessed_headers
from digest.telegram import send_message


TELEGRAM_SAFE_LIMIT = 3900


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _chunks(title: str, lines: list[str]) -> list[str]:
    chunks: list[str] = []
    current = title
    for line in lines:
        addition = f"\n{line}"
        if len(current) + len(addition) > TELEGRAM_SAFE_LIMIT and current != title:
            chunks.append(current)
            current = title + addition
        else:
            current += addition
    if current:
        chunks.append(current)
    return chunks


def run() -> None:
    gmail_address = _require_env("GMAIL_ADDRESS")
    gmail_app_password = _require_env("GMAIL_APP_PASSWORD")
    bot_token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")

    config_path = find_config_path()
    if config_path is None:
        raise SystemExit("Missing config.yml (or config.example.yml)")
    cfg = load_config(config_path)
    errors: list[str] = []

    for sender in cfg.mail.senders:
        try:
            messages = fetch_unprocessed_headers(
                gmail_address,
                gmail_app_password,
                cfg.mail.label,
                sender.from_addr,
                cfg.mail.processed_label,
                cfg.mail.lookback_days,
                cfg.mail.max_messages,
            )
            if not messages:
                print(f"{sender.name}: no new mail", flush=True)
                continue

            title = f"{sender.name} — new newsletter mail"
            lines = [
                f"• {message.subject}\n  {message.date}".rstrip()
                for message in messages
            ]
            for part in _chunks(title, lines):
                send_message(bot_token, chat_id, part)

            apply_processed_label(
                gmail_address,
                gmail_app_password,
                cfg.mail.label,
                cfg.mail.processed_label,
                [message.uid for message in messages],
            )
            print(f"{sender.name}: sent {len(messages)} message header(s)", flush=True)
        except Exception as exc:
            errors.append(f"{sender.name}: {exc}")
            print(f"error: {sender.name}: {exc}", file=sys.stderr, flush=True)

    if errors:
        raise RuntimeError("One or more senders failed: " + "; ".join(errors))


def main() -> None:
    try:
        run()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

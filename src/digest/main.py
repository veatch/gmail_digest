"""One digest run: connect to Gmail, report inbox count on Telegram."""

from __future__ import annotations

import os
import sys

from digest.config import find_config_path, load_config
from digest.mail import inbox_message_count
from digest.telegram import send_message


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def run() -> None:
    gmail_address = _require_env("GMAIL_ADDRESS")
    gmail_app_password = _require_env("GMAIL_APP_PASSWORD")
    bot_token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")

    config_path = find_config_path()
    config_note = "no config.yml"
    if config_path is not None:
        cfg = load_config(config_path)
        sender_n = len(cfg.mail.senders)
        sync = "on" if cfg.upstream.auto_sync else "off"
        config_note = (
            f"{config_path.name}: label={cfg.mail.label!r}, "
            f"{sender_n} sender filter(s), upstream.auto_sync={sync}"
        )

    count = inbox_message_count(gmail_address, gmail_app_password)
    text = (
        f"Gmail OK — inbox has {count} message{'s' if count != 1 else ''}.\n"
        f"Config: {config_note}"
    )
    send_message(bot_token, chat_id, text)
    print(text, flush=True)


def main() -> None:
    try:
        run()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

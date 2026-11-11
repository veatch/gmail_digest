"""Send one Gemini digest per configured sender with new newsletter mail."""

from __future__ import annotations

import html
import os
from pathlib import Path
import sys

from digest.config import find_config_path, load_config
from digest.llm import summarize_sender
from digest.mail import apply_processed_label, fetch_unprocessed_messages
from digest.telegram import send_message


TELEGRAM_SAFE_LIMIT = 3900
BODY_CHAR_LIMIT = 8000
STATE_ROOT = Path("state")


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _read_guidance(path: Path, starter: str) -> str:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(starter, encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def _load_prompt() -> str:
    path = Path(__file__).parent / "prompts" / "digest.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing shared digest prompt: {path}")
    return path.read_text(encoding="utf-8").strip()


def run() -> None:
    gmail_address = _require_env("GMAIL_ADDRESS")
    gmail_app_password = _require_env("GMAIL_APP_PASSWORD")
    gemini_api_key = _require_env("GEMINI_API_KEY")
    bot_token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")

    config_path = find_config_path()
    if config_path is None:
        raise SystemExit("Missing config.yml (or config.example.yml)")
    cfg = load_config(config_path)
    prompt_template = _load_prompt()
    global_guidance = _read_guidance(
        STATE_ROOT / "profile.md",
        "# Global newsletter preferences\n\n"
        "No preferences recorded yet. Keep the digest broadly useful and "
        "include an occasional worthwhile story outside narrow preferences.\n",
    )
    errors: list[str] = []

    for sender in cfg.mail.senders:
        try:
            messages = fetch_unprocessed_messages(
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

            sender_guidance = _read_guidance(
                STATE_ROOT / "senders" / f"{sender.slug}.md",
                f"# {sender.name} preferences\n\n"
                "No sender-specific preferences recorded yet.\n",
            )
            editions = [
                {
                    "subject": message.subject,
                    "date": message.date,
                    "body": message.body[:BODY_CHAR_LIMIT],
                }
                for message in messages
            ]
            summary = summarize_sender(
                gemini_api_key,
                sender.name,
                prompt_template,
                global_guidance,
                sender_guidance,
                editions,
            )
            telegram_text = (
                f"<b>{html.escape(sender.name)}</b>\n\n{html.escape(summary)}"
            )
            if len(telegram_text) > TELEGRAM_SAFE_LIMIT:
                raise RuntimeError(
                    f"Gemini response is too long for one Telegram message "
                    f"({len(telegram_text)} characters)"
                )

            send_message(bot_token, chat_id, telegram_text, parse_mode="HTML")
            apply_processed_label(
                gmail_address,
                gmail_app_password,
                cfg.mail.label,
                cfg.mail.processed_label,
                [message.uid for message in messages],
            )
            print(f"{sender.name}: sent digest for {len(messages)} edition(s)", flush=True)
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

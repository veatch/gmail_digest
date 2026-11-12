"""Apply trusted Telegram messages to global or per-sender guidance."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from digest.config import SenderConfig
from digest.llm import rewrite_guidance
from digest.telegram import get_updates, send_message


MAX_UPDATES_PER_RUN = 10


def _next_offset(path: Path) -> int:
    if not path.is_file():
        return 0
    state = json.loads(path.read_text(encoding="utf-8"))
    return max(0, int(state.get("next_offset", 0)))


def _save_offset(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"next_offset": offset}, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _sender_feedback(
    text: str, senders: list[SenderConfig]
) -> tuple[SenderConfig | None, str, bool]:
    """Return sender, feedback, and whether an explicit sender was unknown."""
    message = text.strip()
    explicit = re.match(r"^for\s+(.+?)\s*[:,]\s*(.+)$", message, re.IGNORECASE)
    if explicit:
        name, feedback = explicit.groups()
        if name.casefold() == "global":
            return None, feedback.strip(), False
        sender = _resolve_sender(name, senders)
        return sender, feedback.strip(), sender is None

    alias_matches = sorted(
        (
            (alias, sender)
            for sender in senders
            for alias in _sender_aliases(sender)
            if message[: len(alias)].casefold() == alias.casefold()
            and len(message) > len(alias)
            and message[len(alias)] in ":,"
        ),
        key=lambda match: len(match[0]),
        reverse=True,
    )
    if alias_matches:
        alias, sender = alias_matches[0]
        feedback = message[len(alias) + 1 :].strip()
        matching_senders = {
            candidate.name
            for candidate_alias, candidate in alias_matches
            if len(candidate_alias) == len(alias)
        }
        if feedback and len(matching_senders) == 1:
            return sender, feedback, False
        if feedback:
            return None, feedback, True

    global_match = re.match(r"^global\s*[:,]\s*(.+)$", message, re.IGNORECASE)
    if global_match:
        return None, global_match.group(1).strip(), False
    return None, message, False


def _sender_aliases(sender: SenderConfig) -> set[str]:
    """Include full name and meaningful components of "Name by Author" labels."""
    aliases = {sender.name.strip()}
    aliases.update(
        component.strip()
        for component in re.split(r"\s+by\s+", sender.name, flags=re.IGNORECASE)
        if component.strip()
    )
    return aliases


def _resolve_sender(name: str, senders: list[SenderConfig]) -> SenderConfig | None:
    normalized = " ".join(name.casefold().split())
    matches = [
        sender
        for sender in senders
        if normalized
        in {" ".join(alias.casefold().split()) for alias in _sender_aliases(sender)}
    ]
    return matches[0] if len(matches) == 1 else None


def _ack(bot_token: str, chat_id: str, text: str) -> None:
    try:
        send_message(bot_token, chat_id, text)
    except Exception as exc:
        print(f"warning: Telegram feedback acknowledgment failed: {exc}", flush=True)


def _guidance_path(state_root: Path, sender: SenderConfig | None) -> Path:
    if sender is None:
        return state_root / "profile.md"
    return state_root / "senders" / f"{sender.slug}.md"


def process_telegram_feedback(
    bot_token: str,
    expected_chat_id: str,
    api_key: str,
    senders: list[SenderConfig],
    state_root: Path,
) -> list[str]:
    """Poll Telegram and rewrite guidance for messages from the trusted chat."""
    offset_path = state_root / "telegram.json"
    try:
        offset = _next_offset(offset_path)
        updates = get_updates(bot_token, offset)[:MAX_UPDATES_PER_RUN]
    except Exception as exc:
        return [f"Telegram feedback poll failed: {exc}"]

    errors: list[str] = []
    for update in updates:
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            continue
        try:
            message = update.get("message")
            if not isinstance(message, dict):
                _save_offset(offset_path, update_id + 1)
                continue

            chat = message.get("chat")
            incoming_chat_id = chat.get("id") if isinstance(chat, dict) else None
            if str(incoming_chat_id) != expected_chat_id:
                _save_offset(offset_path, update_id + 1)
                continue

            text = message.get("text")
            if not isinstance(text, str) or not text.strip():
                _save_offset(offset_path, update_id + 1)
                continue
            text = text.strip()

            if text.startswith("/"):
                _save_offset(offset_path, update_id + 1)
                if text.split(maxsplit=1)[0].split("@", maxsplit=1)[0] == "/start":
                    _ack(
                        bot_token,
                        expected_chat_id,
                        "Send a preference to update the global guidance. For a "
                        "newsletter, use `for Sender Name, ...` or `Sender Name: ...`.",
                    )
                continue

            sender, feedback, unknown_sender = _sender_feedback(text, senders)
            if unknown_sender:
                _save_offset(offset_path, update_id + 1)
                _ack(
                    bot_token,
                    expected_chat_id,
                    "I couldn't match that newsletter name, so I left your "
                    "guidance unchanged. Check the configured sender name and "
                    "try `for Sender Name, ...`.",
                )
                continue

            if not feedback:
                _save_offset(offset_path, update_id + 1)
                continue

            target_path = _guidance_path(state_root, sender)
            current = (
                target_path.read_text(encoding="utf-8")
                if target_path.is_file()
                else ""
            )
            target_name = f"sender {sender.name!r}" if sender else "global profile"
            revised = rewrite_guidance(api_key, target_name, current, feedback).strip()
            if not revised:
                raise RuntimeError("Gemini returned empty preference guidance")

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
            changelog_name = (
                f"{timestamp}-{sender.slug}-{update_id}.md"
                if sender
                else f"{timestamp}-profile-{update_id}.md"
            )
            changelog_path = state_root / "changelog" / changelog_name
            changelog_path.parent.mkdir(parents=True, exist_ok=True)
            changelog_path.write_text(
                f"# Previous {target_name} guidance\n\n{current.strip()}\n",
                encoding="utf-8",
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(revised + "\n", encoding="utf-8")
            _save_offset(offset_path, update_id + 1)

            updated_target = sender.name if sender else "global"
            _ack(
                bot_token,
                expected_chat_id,
                f"Updated {updated_target} newsletter guidance.",
            )
            print(f"Telegram feedback updated {target_name}", flush=True)
        except Exception as exc:
            errors.append(f"Telegram update {update_id}: {exc}")
            print(
                f"error: Telegram update {update_id}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            # Keep this update unacknowledged so the next run retries it.
            break
    return errors

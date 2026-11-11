"""Read and label newsletter headers through Gmail's IMAP extensions."""

from __future__ import annotations

import email
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message
from html.parser import HTMLParser
import imaplib


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


@dataclass(frozen=True)
class NewsletterMessage:
    uid: bytes
    subject: str
    date: str
    body: str


class _HTMLText(HTMLParser):
    """Extract visible text while dropping non-content HTML sections."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "head", "noscript"}:
            self.hidden_depth += 1
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _message_body(message: Message) -> str:
    plain: list[str] = []
    html: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain.append(_decode_part(part))
        elif content_type == "text/html":
            html.append(_decode_part(part))
    raw = "\n".join(plain) if plain else "\n".join(html)
    if not plain and html:
        parser = _HTMLText()
        parser.feed(raw)
        raw = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _imap_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fetch_unprocessed_messages(
    address: str,
    app_password: str,
    folder: str,
    from_addr: str,
    processed_label: str,
    lookback_days: int,
    max_messages: int,
) -> list[NewsletterMessage]:
    """Fetch recent message bodies for one sender's mail not yet labeled."""
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        client.login(address, app_password)
        status, data = client.select(_imap_quote(folder), readonly=False)
        if status != "OK":
            raise RuntimeError(f"Failed to open {folder!r}: {status} {data!r}")

        query = (
            f'from:{from_addr} newer_than:{lookback_days}d '
            f'-label:{processed_label}'
        )
        status, data = client.uid("SEARCH", None, "X-GM-RAW", _imap_quote(query))
        if status != "OK":
            raise RuntimeError(f"Gmail search failed: {status} {data!r}")
        uids = data[0].split()[-max_messages:]

        messages: list[NewsletterMessage] = []
        for uid in uids:
            status, parts = client.uid("FETCH", uid, "(BODY.PEEK[])")
            if status != "OK":
                raise RuntimeError(f"Failed to fetch message {uid!r}: {status}")
            raw_header = next(
                (part[1] for part in parts if isinstance(part, tuple)), b""
            )
            parsed = email.message_from_bytes(raw_header)
            subject = str(make_header(decode_header(parsed.get("Subject", ""))))
            messages.append(
                NewsletterMessage(
                    uid=uid,
                    subject=subject or "(no subject)",
                    date=parsed.get("Date", ""),
                    body=_message_body(parsed),
                )
            )
        return messages
    finally:
        try:
            client.logout()
        except Exception:
            pass


def apply_processed_label(
    address: str,
    app_password: str,
    folder: str,
    label: str,
    uids: list[bytes],
) -> None:
    """Apply the configured Gmail label to delivered messages by UID."""
    if not uids:
        return
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        client.login(address, app_password)
        status, data = client.select(_imap_quote(folder), readonly=False)
        if status != "OK":
            raise RuntimeError(f"Failed to open {folder!r}: {status} {data!r}")
        uid_set = b",".join(uids)
        status, data = client.uid(
            "STORE", uid_set, "+X-GM-LABELS", f"({_imap_quote(label)})"
        )
        if status != "OK":
            raise RuntimeError(f"Failed to apply label {label!r}: {status} {data!r}")
    finally:
        try:
            client.logout()
        except Exception:
            pass

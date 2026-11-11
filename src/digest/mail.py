"""Read and label newsletter headers through Gmail's IMAP extensions."""

from __future__ import annotations

import email
from dataclasses import dataclass
from email.header import decode_header, make_header
import imaplib


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


@dataclass(frozen=True)
class NewsletterHeader:
    uid: bytes
    subject: str
    date: str


def _imap_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fetch_unprocessed_headers(
    address: str,
    app_password: str,
    folder: str,
    from_addr: str,
    processed_label: str,
    lookback_days: int,
    max_messages: int,
) -> list[NewsletterHeader]:
    """Fetch header fields for recent mail from one sender not yet labeled."""
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

        messages: list[NewsletterHeader] = []
        for uid in uids:
            status, parts = client.uid(
                "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])"
            )
            if status != "OK":
                raise RuntimeError(f"Failed to fetch message {uid!r}: {status}")
            raw_header = next(
                (part[1] for part in parts if isinstance(part, tuple)), b""
            )
            parsed = email.message_from_bytes(raw_header)
            subject = str(make_header(decode_header(parsed.get("Subject", ""))))
            messages.append(
                NewsletterHeader(uid=uid, subject=subject or "(no subject)", date=parsed.get("Date", ""))
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

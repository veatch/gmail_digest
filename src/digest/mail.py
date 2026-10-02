"""IMAP access to Gmail (read-only checks for now)."""

from __future__ import annotations

import imaplib


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def inbox_message_count(address: str, app_password: str) -> int:
    """Log in over IMAP SSL and return the INBOX message count."""
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        client.login(address, app_password)
        status, data = client.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError(f"Failed to open INBOX: {status} {data!r}")
        # select returns the message count as bytes in data[0].
        return int(data[0])
    finally:
        try:
            client.logout()
        except Exception:
            pass

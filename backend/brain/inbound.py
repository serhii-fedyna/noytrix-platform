from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import datetime, timezone
from email.header import decode_header
from email.message import Message

from auth.emailer import _smtp_config

from .reports import notify_inbound_reply
from .repository import draft_delivery_snapshot, record_inbound_reply, runtime_state, set_runtime_state


STATE_KEY = "brain_inbound_imap_uid"
_DRAFT_ID_RE = re.compile(r"noytrix-brain-(\d+)@", re.IGNORECASE)
_BOUNCE_RE = re.compile(r"mailer-daemon|postmaster|delivery status|undeliver|failure|returned mail", re.IGNORECASE)


def _decode(value: str | None) -> str:
    parts: list[str] = []
    for chunk, charset in decode_header(value or ""):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return "".join(parts).strip()


def _body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or "").lower():
                raw = part.get_payload(decode=True) or b""
                return raw.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    raw = message.get_payload(decode=True) or b""
    return raw.decode(message.get_content_charset() or "utf-8", errors="replace")


def _draft_id(message: Message) -> int | None:
    headers = " ".join(str(message.get(key) or "") for key in ("In-Reply-To", "References", "Message-ID", "X-Noytrix-Brain-Draft-ID"))
    explicit = str(message.get("X-Noytrix-Brain-Draft-ID") or "").strip()
    if explicit.isdigit():
        return int(explicit)
    match = _DRAFT_ID_RE.search(headers)
    return int(match.group(1)) if match else None


def inbox_available() -> bool:
    cfg = _smtp_config()
    host = str(os.getenv("NOYTRIX_BRAIN_IMAP_HOST") or os.getenv("IMAP_HOST") or "").strip()
    if not host and cfg["host"] == "smtp.gmail.com":
        host = "imap.gmail.com"
    return bool(host and cfg["user"] and cfg["password"])


def process_inbound_mail_once() -> int:
    """Watch new mailbox traffic and notify only replies tied to an outbound Brain draft."""
    cfg = _smtp_config()
    host = str(os.getenv("NOYTRIX_BRAIN_IMAP_HOST") or os.getenv("IMAP_HOST") or "").strip()
    if not host and cfg["host"] == "smtp.gmail.com":
        host = "imap.gmail.com"
    if not host or not cfg["user"] or not cfg["password"]:
        return 0
    port = int(os.getenv("NOYTRIX_BRAIN_IMAP_PORT", "993") or "993")
    with imaplib.IMAP4_SSL(host, port, timeout=20) as client:
        client.login(cfg["user"], cfg["password"])
        client.select("INBOX", readonly=True)
        status, data = client.uid("search", None, "ALL")
        if status != "OK":
            return 0
        uids = [item.decode("ascii") for item in (data[0] or b"").split() if item]
        if not uids:
            return 0
        previous = runtime_state(STATE_KEY)
        if not previous:
            set_runtime_state(STATE_KEY, uids[-1])
            return 0
        new_uids = [uid for uid in uids if int(uid) > int(previous)]
        processed = 0
        for uid in new_uids:
            status, payload = client.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue
            message = email.message_from_bytes(payload[0][1])
            draft_id = _draft_id(message)
            if not draft_id:
                continue
            sender = _decode(message.get("From"))
            subject = _decode(message.get("Subject"))
            snippet = " ".join(_body(message).split())[:1000]
            kind = "bounce" if _BOUNCE_RE.search(f"{sender} {subject}") else "reply"
            received_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            if record_inbound_reply(imap_uid=uid, draft_id=draft_id, kind=kind, sender=sender, subject=subject, snippet=snippet, received_at=received_at):
                processed += 1
                if kind == "reply":
                    draft = draft_delivery_snapshot(draft_id) or {}
                    notify_inbound_reply(
                        prospect_name=str(draft.get("prospect_name") or "Noytrix contact"),
                        sender=sender,
                        subject=subject,
                        snippet=snippet,
                        kind="job" if draft.get("pipeline") == "serhii_job_search" else "partnership",
                    )
        set_runtime_state(STATE_KEY, uids[-1])
        return processed

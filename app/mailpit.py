"""Fetch a message from Mailpit and download its PDF attachment."""
import os

import httpx


def _base() -> str:
    return os.getenv("MAILPIT_URL", "http://localhost:8025").rstrip("/")


def get_pdf(message_id: str) -> tuple[bytes, str] | None:
    """Return (pdf_bytes, filename) for the first PDF attachment, or None if the mail has none.

    Raises httpx.HTTPStatusError (e.g. 404) if Mailpit does not know the message id.
    """
    with httpx.Client(base_url=_base(), timeout=30) as c:
        r = c.get(f"/api/v1/message/{message_id}")
        r.raise_for_status()
        for att in r.json().get("Attachments") or []:
            name = att.get("FileName") or ""
            if att.get("ContentType") == "application/pdf" or name.lower().endswith(".pdf"):
                part = c.get(f"/api/v1/message/{message_id}/part/{att['PartID']}")
                part.raise_for_status()
                return part.content, name
    return None

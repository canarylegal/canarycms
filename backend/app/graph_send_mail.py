"""Microsoft Graph sendMail for automated firm alerts (application permissions)."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.graph_mail import app_access_token

log = logging.getLogger(__name__)


def send_graph_mail_message(
    db: Session,
    *,
    send_mailbox: str,
    to_email: str,
    subject: str,
    body_text: str,
    from_name: str | None = None,
    save_to_sent_items: bool = True,
) -> None:
    """Send plain-text mail as ``send_mailbox`` via Graph ``/users/{mailbox}/sendMail``."""
    mailbox = (send_mailbox or "").strip()
    to_addr = (to_email or "").strip()
    if not mailbox:
        raise RuntimeError("Graph send mailbox is not configured (Admin → E-mail → Alert notifications).")
    if not to_addr:
        raise RuntimeError("Recipient e-mail is required.")

    token = app_access_token(db)
    url = f"https://graph.microsoft.com/v1.0/users/{quote(mailbox)}/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": to_addr}}],
        },
        "saveToSentItems": bool(save_to_sent_items),
    }
    display = (from_name or "").strip()
    if display:
        payload["message"]["from"] = {"emailAddress": {"name": display, "address": mailbox}}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(url, json=payload, headers=headers)
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Microsoft Graph to send mail: {e}") from e
    if res.status_code >= 400:
        txt = (res.text or "").strip()
        raise RuntimeError(f"Microsoft Graph sendMail failed ({res.status_code}): {txt[:700]}")

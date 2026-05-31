"""Outbound firm e-mail: Graph or SMTP for calendar and portal alerts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.email_integration_settings import get_email_integration_settings, graph_mail_effective_configured
from app.graph_send_mail import send_graph_mail_message
from app.smtp_notification_settings import get_smtp_notification_settings
from app.smtp_send import send_smtp_message

log = logging.getLogger(__name__)

AlertTransportMode = Literal["auto", "graph", "smtp"]
ResolvedTransport = Literal["graph", "smtp"]

ALERT_TRANSPORT_AUTO = "auto"
ALERT_TRANSPORT_GRAPH = "graph"
ALERT_TRANSPORT_SMTP = "smtp"


@dataclass(frozen=True)
class FirmEmailMessage:
    to_email: str
    subject: str
    body_text: str


def _graph_alert_ready(db: Session) -> bool:
    if not graph_mail_effective_configured(db):
        return False
    row = get_email_integration_settings(db)
    return bool((row.graph_send_mailbox or "").strip())


def _smtp_alert_ready(db: Session) -> bool:
    row = get_smtp_notification_settings(db)
    if not row.enabled:
        return False
    if not (row.host or "").strip():
        return False
    if not (row.from_email or "").strip():
        return False
    return True


def alerts_enabled(db: Session) -> bool:
    return bool(get_email_integration_settings(db).alerts_enabled)


def resolve_alert_transport(db: Session) -> ResolvedTransport | None:
    """Pick Graph or SMTP for the next alert, or None if alerts cannot be sent."""
    if not alerts_enabled(db):
        return None
    row = get_email_integration_settings(db)
    mode = (row.alert_transport or ALERT_TRANSPORT_AUTO).strip().lower()
    if mode == ALERT_TRANSPORT_GRAPH:
        return "graph" if _graph_alert_ready(db) else None
    if mode == ALERT_TRANSPORT_SMTP:
        return "smtp" if _smtp_alert_ready(db) else None
    if _graph_alert_ready(db):
        return "graph"
    if _smtp_alert_ready(db):
        return "smtp"
    return None


def firm_email_status(db: Session) -> dict[str, object]:
    """Admin UI: which transports are configured and which would be used."""
    transport = resolve_alert_transport(db)
    row = get_email_integration_settings(db)
    return {
        "alerts_enabled": alerts_enabled(db),
        "alert_transport": row.alert_transport or ALERT_TRANSPORT_AUTO,
        "graph_send_mailbox": (row.graph_send_mailbox or "").strip() or None,
        "graph_send_from_name": (row.graph_send_from_name or "").strip() or None,
        "graph_ready": _graph_alert_ready(db),
        "smtp_ready": _smtp_alert_ready(db),
        "effective_transport": transport,
    }


def send_firm_email(db: Session, message: FirmEmailMessage) -> ResolvedTransport:
    """Send using configured alert transport. Raises if alerts are not configured."""
    transport = resolve_alert_transport(db)
    if transport is None:
        raise RuntimeError(
            "Automated e-mail alerts are disabled or not configured (Admin → E-mail → Alert notifications).",
        )
    to_email = message.to_email.strip()
    if transport == "graph":
        row = get_email_integration_settings(db)
        send_graph_mail_message(
            db,
            send_mailbox=(row.graph_send_mailbox or "").strip(),
            to_email=to_email,
            subject=message.subject,
            body_text=message.body_text,
            from_name=(row.graph_send_from_name or "").strip() or None,
        )
        return "graph"
    send_smtp_message(db, to_email=to_email, subject=message.subject, body=message.body_text)
    return "smtp"


def try_send_firm_email(db: Session, message: FirmEmailMessage) -> ResolvedTransport | None:
    """Best-effort send for hooks; logs and returns None on skip/failure."""
    try:
        return send_firm_email(db, message)
    except Exception:
        log.exception("firm_email: send failed to=%s subject=%s", message.to_email, message.subject[:80])
        return None

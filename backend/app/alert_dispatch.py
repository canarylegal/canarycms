"""Dispatch automated e-mail alerts (internal staff and external portal contacts)."""

from __future__ import annotations

import enum
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.alert_templates import (
    calendar_event_reminder,
    portal_contact_access_granted,
    portal_contact_files_added,
    portal_contact_folder_granted,
    portal_login_otp,
    portal_staff_upload,
)
from app.audit import log_event
from app.canary_public_url import canary_public_url
from app.firm_email_service import FirmEmailMessage, resolve_alert_transport, try_send_firm_email
from app.models import FirmSettings

log = logging.getLogger(__name__)


class AlertKind(str, enum.Enum):
    calendar_event_reminder = "calendar_event_reminder"
    portal_staff_upload = "portal_staff_upload"
    portal_contact_access = "portal_contact_access"
    portal_contact_folder = "portal_contact_folder"
    portal_contact_files_added = "portal_contact_files_added"
    portal_login_otp = "portal_login_otp"


def firm_alerts_configured(db: Session) -> bool:
    return resolve_alert_transport(db) is not None


def _firm_name(db: Session) -> str:
    firm = db.get(FirmSettings, 1)
    if not firm:
        return ""
    return (firm.trading_name or "").strip() or (firm.registered_company_name or "").strip() or ""


def portal_public_url() -> str:
    base = canary_public_url().rstrip("/")
    return f"{base}/portal"


def dispatch_alert(
    db: Session,
    kind: AlertKind,
    *,
    to_email: str,
    context: dict[str, Any],
    actor_user_id: uuid.UUID | None = None,
) -> bool:
    """Build template, send via firm e-mail transport, audit. Returns True if sent."""
    addr = (to_email or "").strip()
    if not addr:
        return False

    firm = _firm_name(db)
    body_html: str | None = None
    if kind == AlertKind.calendar_event_reminder:
        subject, body = calendar_event_reminder(
            title=str(context.get("title") or ""),
            anchor_label=str(context.get("anchor_label") or "unknown"),
        )
    elif kind == AlertKind.portal_staff_upload:
        subject, body, body_html = portal_staff_upload(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            area_label=str(context.get("area_label") or "Documents"),
            filename=str(context.get("filename") or "file"),
        )
    elif kind == AlertKind.portal_contact_access:
        subject, body, body_html = portal_contact_access_granted(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            portal_url=str(context.get("portal_url") or portal_public_url()),
            access_code=str(context.get("access_code") or ""),
        )
    elif kind == AlertKind.portal_contact_folder:
        subject, body, body_html = portal_contact_folder_granted(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            area_label=str(context.get("area_label") or "Documents"),
            portal_url=str(context.get("portal_url") or portal_public_url()),
        )
    elif kind == AlertKind.portal_contact_files_added:
        filenames = context.get("filenames") or []
        if isinstance(filenames, str):
            filenames = [filenames]
        subject, body, body_html = portal_contact_files_added(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            area_label=str(context.get("area_label") or "Documents"),
            filenames=[str(x) for x in filenames],
            portal_url=str(context.get("portal_url") or portal_public_url()),
        )
    elif kind == AlertKind.portal_login_otp:
        subject, body, body_html = portal_login_otp(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            portal_url=str(context.get("portal_url") or portal_public_url()),
            otp_code=str(context.get("otp_code") or ""),
        )
    else:
        log.warning("alert_dispatch: unknown kind %s", kind)
        return False

    transport = try_send_firm_email(
        db,
        FirmEmailMessage(to_email=addr, subject=subject, body_text=body, body_html=body_html),
    )
    if transport is None:
        return False

    log_event(
        db,
        actor_user_id=actor_user_id,
        action=f"alert.email.{kind.value}",
        entity_type="email",
        entity_id=addr,
        meta={"kind": kind.value, "transport": transport, **{k: str(v) for k, v in context.items() if k != "access_code"}},
    )
    db.commit()
    return True


def notify_portal_contacts_files_added(
    db: Session,
    *,
    case_id: uuid.UUID,
    folder_path: str,
    filenames: list[str],
    exclude_contact_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> int:
    """Batch notify — one e-mail per contact listing all filenames."""
    from app.portal_notifications import notify_portal_contacts_files_added_batch

    result = notify_portal_contacts_files_added_batch(
        db,
        case_id=case_id,
        folder_path=folder_path,
        filenames=filenames,
        actor_user_id=actor_user_id,
    )
    return result.contacts_notified

"""Dispatch automated e-mail alerts (internal staff and external portal contacts)."""

from __future__ import annotations

import enum
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alert_templates import (
    calendar_event_reminder,
    portal_contact_access_granted,
    portal_contact_files_added,
    portal_contact_folder_granted,
    portal_staff_upload,
)
from app.audit import log_event
from app.canary_public_url import canary_public_url
from app.firm_email_service import FirmEmailMessage, try_send_firm_email
from app.models import Contact, ContactPortalGrant, FirmSettings
from app.portal_service import contact_display_name, default_grant_label, file_folder_in_grant, grant_is_active

log = logging.getLogger(__name__)


class AlertKind(str, enum.Enum):
    calendar_event_reminder = "calendar_event_reminder"
    portal_staff_upload = "portal_staff_upload"
    portal_contact_access = "portal_contact_access"
    portal_contact_folder = "portal_contact_folder"
    portal_contact_files_added = "portal_contact_files_added"


def _firm_name(db: Session) -> str:
    firm = db.get(FirmSettings, 1)
    if not firm:
        return ""
    return (firm.trading_name or "").strip() or (firm.registered_company_name or "").strip() or ""


def _portal_url() -> str:
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
    if kind == AlertKind.calendar_event_reminder:
        subject, body = calendar_event_reminder(
            title=str(context.get("title") or ""),
            anchor_label=str(context.get("anchor_label") or "unknown"),
        )
    elif kind == AlertKind.portal_staff_upload:
        subject, body = portal_staff_upload(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            area_label=str(context.get("area_label") or "Documents"),
            filename=str(context.get("filename") or "file"),
        )
    elif kind == AlertKind.portal_contact_access:
        subject, body = portal_contact_access_granted(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            portal_url=str(context.get("portal_url") or _portal_url()),
            access_code=str(context.get("access_code") or ""),
        )
    elif kind == AlertKind.portal_contact_folder:
        subject, body = portal_contact_folder_granted(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            area_label=str(context.get("area_label") or "Documents"),
            portal_url=str(context.get("portal_url") or _portal_url()),
        )
    elif kind == AlertKind.portal_contact_files_added:
        filenames = context.get("filenames") or []
        if isinstance(filenames, str):
            filenames = [filenames]
        subject, body = portal_contact_files_added(
            firm_name=firm,
            contact_name=str(context.get("contact_name") or "Client"),
            area_label=str(context.get("area_label") or "Documents"),
            filenames=[str(x) for x in filenames],
            portal_url=str(context.get("portal_url") or _portal_url()),
        )
    else:
        log.warning("alert_dispatch: unknown kind %s", kind)
        return False

    transport = try_send_firm_email(db, FirmEmailMessage(to_email=addr, subject=subject, body_text=body))
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
) -> int:
    """E-mail portal contacts with access to ``folder_path`` that new files were added."""
    if not filenames:
        return 0
    grants = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.case_id == case_id)).scalars().all()
    sent = 0
    seen: set[uuid.UUID] = set()
    portal_url = _portal_url()
    for grant in grants:
        if not grant_is_active(grant):
            continue
        if not file_folder_in_grant(folder_path, grant.folder_path):
            continue
        if grant.contact_id in seen:
            continue
        if exclude_contact_id and grant.contact_id == exclude_contact_id:
            continue
        contact = db.get(Contact, grant.contact_id)
        if not contact or not (contact.email or "").strip():
            continue
        seen.add(grant.contact_id)
        area = default_grant_label(db, grant)
        if dispatch_alert(
            db,
            AlertKind.portal_contact_files_added,
            to_email=contact.email,
            context={
                "contact_name": contact_display_name(contact),
                "area_label": area,
                "filenames": filenames,
                "portal_url": portal_url,
            },
        ):
            sent += 1
    return sent

"""Portal notification routing: client prefs, staff recipients, batch file alerts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alert_dispatch import AlertKind, dispatch_alert, firm_alerts_configured, matter_deep_link
from app.case_reference import display_case_number
from app.models import Case, CasePortalStaffRecipient, Contact, ContactPortalAccess, ContactPortalGrant, User
from app.portal_service import contact_display_name, default_grant_label, file_folder_in_grant, grant_is_active


ALERTS_NOT_CONFIGURED_MSG = (
    "Automated e-mail is not configured. Ask an administrator to enable Admin → E-mail → "
    "“Enable automated alert e-mail” and set up Graph or SMTP."
)


def staff_matter_label(case: Case | None) -> str:
    """Matter label for staff alerts (reference + title when available)."""
    if case is None:
        return "matter"
    ref = display_case_number(case.case_number, case.status)
    title = (case.title or "").strip()
    if ref and title and title != ref:
        return f"{ref} — {title}"
    return ref or title or "matter"


def staff_matter_context(db: Session, case_id: uuid.UUID) -> dict[str, str]:
    case = db.get(Case, case_id)
    return {
        "matter_label": staff_matter_label(case),
        "matter_url": matter_deep_link(case_id),
    }


@dataclass(frozen=True)
class PortalNotifyResult:
    contacts_notified: int
    staff_notified: int
    alerts_skipped_reason: str | None = None


def contact_wants_notification(db: Session, contact_id: uuid.UUID, kind: AlertKind) -> bool:
    row = db.execute(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)).scalar_one_or_none()
    if row is None or not row.enabled:
        return False
    if kind == AlertKind.portal_contact_files_added:
        return bool(row.notify_files_added)
    if kind == AlertKind.portal_contact_folder:
        return bool(row.notify_folder_shared)
    if kind in (AlertKind.portal_contact_access, AlertKind.portal_login_otp):
        return True
    return True


def list_portal_staff_recipient_users(db: Session, case_id: uuid.UUID) -> list[User]:
    case = db.get(Case, case_id)
    if case is None:
        return []
    rows = (
        db.execute(select(CasePortalStaffRecipient.user_id).where(CasePortalStaffRecipient.case_id == case_id))
        .scalars()
        .all()
    )
    if rows:
        users = db.execute(select(User).where(User.id.in_(rows), User.is_active.is_(True))).scalars().all()
        return list(users)
    fee = db.get(User, case.fee_earner_user_id)
    if fee and fee.is_active and (fee.email or "").strip():
        return [fee]
    return []


def set_portal_staff_recipients(db: Session, case_id: uuid.UUID, user_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    existing = (
        db.execute(select(CasePortalStaffRecipient).where(CasePortalStaffRecipient.case_id == case_id)).scalars().all()
    )
    for row in existing:
        db.delete(row)
    kept: list[uuid.UUID] = []
    for uid in user_ids:
        u = db.get(User, uid)
        if u is None or not u.is_active:
            continue
        db.add(CasePortalStaffRecipient(case_id=case_id, user_id=uid))
        kept.append(uid)
    db.flush()
    return kept


def notify_portal_contacts_files_added_batch(
    db: Session,
    *,
    case_id: uuid.UUID,
    folder_path: str,
    filenames: list[str],
    actor_user_id: uuid.UUID | None = None,
) -> PortalNotifyResult:
    """One e-mail per contact listing all new filenames."""
    names = [f.strip() for f in filenames if f and f.strip()]
    if not names:
        return PortalNotifyResult(0, 0, None)
    from app.portal_case import case_portal_enabled

    if not case_portal_enabled(db, case_id):
        return PortalNotifyResult(0, 0, None)
    if not firm_alerts_configured(db):
        return PortalNotifyResult(0, 0, ALERTS_NOT_CONFIGURED_MSG)

    from app.alert_dispatch import portal_public_url as _portal_url

    grants = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.case_id == case_id)).scalars().all()
    portal_url = _portal_url()
    sent = 0
    seen: set[uuid.UUID] = set()
    area_label = None
    for grant in grants:
        if not grant_is_active(grant):
            continue
        if not file_folder_in_grant(file_folder=folder_path, grant_folder=grant.folder_path):
            continue
        if grant.contact_id in seen:
            continue
        if not contact_wants_notification(db, grant.contact_id, AlertKind.portal_contact_files_added):
            seen.add(grant.contact_id)
            continue
        contact = db.get(Contact, grant.contact_id)
        if not contact or not (contact.email or "").strip():
            seen.add(grant.contact_id)
            continue
        seen.add(grant.contact_id)
        area = default_grant_label(db, grant)
        if area_label is None:
            area_label = area
        if dispatch_alert(
            db,
            AlertKind.portal_contact_files_added,
            to_email=contact.email,
            context={
                "contact_name": contact_display_name(contact),
                "area_label": area,
                "filenames": names,
                "portal_url": portal_url,
            },
            actor_user_id=actor_user_id,
        ):
            sent += 1
    return PortalNotifyResult(sent, 0, None)


def notify_portal_staff_client_upload(
    db: Session,
    *,
    case_id: uuid.UUID,
    contact: Contact,
    grant: ContactPortalGrant,
    filename: str,
) -> PortalNotifyResult:
    if not firm_alerts_configured(db):
        return PortalNotifyResult(0, 0, ALERTS_NOT_CONFIGURED_MSG)
    area = default_grant_label(db, grant)
    matter_ctx = staff_matter_context(db, case_id)
    staff_sent = 0
    for user in list_portal_staff_recipient_users(db, case_id):
        email = (user.email or "").strip()
        if not email:
            continue
        if dispatch_alert(
            db,
            AlertKind.portal_staff_upload,
            to_email=email,
            context={
                "contact_name": contact_display_name(contact),
                "area_label": area,
                "filename": filename,
                **matter_ctx,
            },
        ):
            staff_sent += 1
    return PortalNotifyResult(0, staff_sent, None)


def notify_portal_staff_form_completed(
    db: Session,
    *,
    case_id: uuid.UUID,
    contact: Contact,
    form_name: str,
    matter_label: str,
) -> PortalNotifyResult:
    if not firm_alerts_configured(db):
        return PortalNotifyResult(0, 0, ALERTS_NOT_CONFIGURED_MSG)
    matter_ctx = staff_matter_context(db, case_id)
    # Prefer staff reference label; fall back to caller-provided client-facing label.
    if not matter_ctx["matter_label"] or matter_ctx["matter_label"] == "matter":
        matter_ctx["matter_label"] = (matter_label or "").strip() or "matter"
    staff_sent = 0
    for user in list_portal_staff_recipient_users(db, case_id):
        email = (user.email or "").strip()
        if not email:
            continue
        if dispatch_alert(
            db,
            AlertKind.portal_form_completed,
            to_email=email,
            context={
                "contact_name": contact_display_name(contact),
                "form_name": form_name,
                **matter_ctx,
            },
        ):
            staff_sent += 1
    return PortalNotifyResult(0, staff_sent, None)

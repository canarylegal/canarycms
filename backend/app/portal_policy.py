"""Portal authorization carried with the request's DB unit of work.

Portal services revalidate at their mutation boundary. SHARE locks serialize that
boundary against staff revocation without serializing independent client reads.
Trusted staff/background service callers have no portal principal.
"""

import uuid
from time import time
from fastapi import HTTPException
from sqlalchemy import select
from app.models import (
    Contact,
    ContactPortalAccess,
    MatterPortalAccess,
    Case,
    FirmSettings,
    PortalMatterBlock,
)
from app.portal_service import portal_access_is_active, matter_portal_access_is_active


def fresh(db, model, identity, *, lock=False):
    stmt = (
        select(model)
        .where(model.id == identity)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update(read=True)
    with db.no_autoflush:
        return db.scalar(stmt)


def validate_preview(db, principal):
    if not principal.staff_preview:
        return
    from app.models import User
    from app.deps import require_case_access
    try:
        staff = fresh(db, User, uuid.UUID(principal.staff_user_id))
        case_id = uuid.UUID(principal.case_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(401, "Preview expired; open a new preview")
    if staff is None or not staff.is_active or principal.staff_version != staff.auth_token_version:
        raise HTTPException(401, "Staff preview access has expired")
    require_case_access(case_id, staff, db)


def authorize(db, case_id, *, signing_request_id=None, resource_kind=None, resource_id=None, lock=False, client_only=False):
    principal = db.info.get("portal_session")
    if principal is None:
        return
    if principal.expires_at is not None and time() >= principal.expires_at:
        raise HTTPException(401, "Session expired — sign in again.")
    if principal.audience == "exchange" and (client_only or signing_request_id):
        raise HTTPException(
            403, "This action is not available for matter exchange access"
        )
    validate_preview(db, principal)
    if principal.case_id and str(case_id) != principal.case_id:
        raise HTTPException(404, "Area not found")
    if principal.invitation:
        if principal.resource_kind == "sign":
            if str(signing_request_id) != principal.signing_request_id:
                raise HTTPException(403, "This invitation is limited to its signing request")
        elif resource_kind != principal.resource_kind or str(resource_id) != principal.resource_id:
            raise HTTPException(403, "This invitation is limited to its form or quote")
        from app.portal_invitation import resolve, coordinates
        try:
            row = resolve(db, principal.invitation, principal.resource_kind, completed=True, lock=lock)
            resolved_case, resolved_contact = coordinates(db, principal.resource_kind, row)
            if str(resolved_case) != str(case_id) or str(resolved_contact) != principal.contact_id:
                raise ValueError("Invitation identity mismatch")
            if principal.resource_kind == "sign" and str(row.signing_request_id) != principal.signing_request_id:
                raise ValueError("Signing identity mismatch")
        except ValueError as exc:
            raise HTTPException(401, str(exc)) from exc
        # Preserve the fresh, locked feature checks used by ordinary portal sessions.
        firm = fresh(db, FirmSettings, 1, lock=lock)
        case = fresh(db, Case, case_id, lock=lock)
        if not case or not case.portal_enabled or (firm and not firm.client_portal_enabled):
            raise HTTPException(403, "Portal is not enabled for this matter.")
        if principal.resource_kind == "sign" and firm and not firm.canary_sign_enabled:
            raise HTTPException(403, "Canary Sign is disabled")
        return
    contact_id = uuid.UUID(principal.contact_id)
    if principal.audience == "exchange" and str(case_id) != principal.case_id:
        raise HTTPException(404, "Area not found")
    if (
        principal.signing_request_id
        and str(signing_request_id) != principal.signing_request_id
    ):
        raise HTTPException(403, "This link is limited to its signing request")
    if not fresh(db, Contact, contact_id, lock=lock):
        raise HTTPException(401, "Portal access is disabled")
    firm = fresh(db, FirmSettings, 1, lock=lock)
    case = fresh(db, Case, case_id, lock=lock)
    if not case or not case.portal_enabled or (firm and not firm.client_portal_enabled):
        raise HTTPException(403, "Portal is not enabled for this matter.")
    if signing_request_id and firm and not firm.canary_sign_enabled:
        raise HTTPException(403, "Canary Sign is disabled")
    model = (
        MatterPortalAccess if principal.audience == "exchange" else ContactPortalAccess
    )
    stmt = select(model).where(model.contact_id == contact_id)
    if model is MatterPortalAccess:
        stmt = stmt.where(model.case_id == case_id)
    if lock:
        stmt = stmt.with_for_update(read=True)
    with db.no_autoflush:
        access = db.scalar(stmt.execution_options(populate_existing=True))
        blocked = db.scalar(
            select(PortalMatterBlock).where(
                PortalMatterBlock.case_id == case_id,
                PortalMatterBlock.contact_id == contact_id,
            )
        )
    active = (
        matter_portal_access_is_active
        if model is MatterPortalAccess
        else portal_access_is_active
    )
    if (
        access is None
        or not active(access)
        or access.session_version != principal.session_version
    ):
        raise HTTPException(401, "Session expired — sign in again.")
    if principal.signing_request_id:
        from app.models import CanarySignRequest, CanarySignRecipient
        from app.timeutil import utcnow
        from datetime import timezone

        req = fresh(db, CanarySignRequest, uuid.UUID(principal.signing_request_id))
        if req is None or req.status.value not in ("pending", "completed"):
            raise HTTPException(403, "Signing request is no longer available")
        expires = (
            req.expires_at.replace(tzinfo=timezone.utc)
            if req.expires_at.tzinfo is None
            else req.expires_at
        )
        if req.status.value == "pending" and expires <= utcnow():
            raise HTTPException(403, "Signing request has expired")
        recipient = db.scalar(
            select(CanarySignRecipient).where(
                CanarySignRecipient.signing_request_id == req.id,
                CanarySignRecipient.contact_id == contact_id,
            )
        )
        if (
            recipient is None
            or recipient.portal_access_version != principal.session_version
        ):
            raise HTTPException(401, "Signing access has expired")
    if blocked:
        raise HTTPException(403, "Portal access to this matter has been revoked")


def visible(db, case_id, *, signing_request_id=None, resource_kind=None, resource_id=None):
    try:
        authorize(db, case_id, signing_request_id=signing_request_id, resource_kind=resource_kind, resource_id=resource_id)
        return True
    except HTTPException:
        return False

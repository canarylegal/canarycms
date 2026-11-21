"""Resource-scoped invitations. Legacy IDs and unversioned JWTs are not credentials."""
import time
import uuid
from datetime import timezone
from jose import jwt, JWTError
from sqlalchemy import select
from app.models import ContactPortalAccess, PortalFormSubmission, QuotePortalDelivery, PortalMatterBlock
from app.security import JWT_SECRET, JWT_ALG, PORTAL_QUOTE_EXCHANGE_TTL_SECONDS
from app.portal_service import portal_access_is_active


def generation(row):
    sent = row.sent_at
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    return sent.isoformat()


def issue(db, kind, row):
    access = db.scalar(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == row.contact_id))
    if access is None or not portal_access_is_active(access):
        raise ValueError("Portal access is not active")
    now = int(time.time())
    return jwt.encode({"purpose": "portal_invitation", "kind": kind, "resource": str(row.id),
        "contact": str(row.contact_id), "case": str(row.case_id), "sv": access.session_version,
        "generation": generation(row), "iat": now, "exp": now + PORTAL_QUOTE_EXCHANGE_TTL_SECONDS},
        JWT_SECRET, algorithm=JWT_ALG)


def resolve(db, token, kind, *, completed=False, lock=False):
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        if claims.get("purpose") != "portal_invitation" or claims.get("kind") != kind:
            raise ValueError()
        model = PortalFormSubmission if kind == "form" else QuotePortalDelivery
        stmt = select(model).where(model.id == uuid.UUID(claims["resource"])).execution_options(populate_existing=True)
        if lock:
            stmt = stmt.with_for_update()
        row = db.scalar(stmt)
        if row is None or claims["contact"] != str(row.contact_id) or claims["case"] != str(row.case_id):
            raise ValueError()
        allowed = ("pending", "completed") if completed and kind == "form" else ("pending", "accepted", "declined") if completed else ("pending",)
        if row.status.value not in allowed or claims["generation"] != generation(row):
            raise ValueError()
        access = db.scalar(select(ContactPortalAccess).where(ContactPortalAccess.contact_id == row.contact_id).execution_options(populate_existing=True))
        if access is None or not portal_access_is_active(access) or access.session_version != claims["sv"]:
            raise ValueError()
        if db.get(PortalMatterBlock, (row.case_id, row.contact_id)):
            raise ValueError()
        from app.portal_case import require_case_portal_enabled
        require_case_portal_enabled(db, row.case_id)
        return row
    except (JWTError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid or expired invitation; sign in or request a new link") from exc

"""Authorize both sides of a global merge before disclosing or changing records."""

import uuid

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.deps import require_case_access
from app.models import (
    Case, CaseAccessRule, CaseContact, CaseInvoice, Contact, ContactPortalAccess,
    ContactPortalGrant, MatterPortalAccess, PortalActivityEvent, PortalMatterBlock,
    PortalFormSubmission, PortalLoginOtp, QuotePortalDelivery, LedgerEntry,
    LedgerAccount, CanarySignRecipient, CanarySignRequest, DocusignSigningRecipient,
    DocusignSigningRequest, User, UserPermissionCategory,
)
from app.portal_grant_views import ContactPortalGrantView

# Include retained, revoked and historical records; never filter by active status.
DIRECT_MATTER_RECORDS = (
    CaseContact, CaseInvoice, ContactPortalGrant, MatterPortalAccess,
    PortalActivityEvent, PortalMatterBlock, PortalFormSubmission, QuotePortalDelivery,
)
INDIRECT_MATTER_RECORDS = (
    (LedgerEntry, 'account_id', LedgerAccount),
    (CanarySignRecipient, 'signing_request_id', CanarySignRequest),
    (DocusignSigningRecipient, 'signing_request_id', DocusignSigningRequest),
    (ContactPortalGrantView, 'grant_id', ContactPortalGrant),
)
GLOBAL_RECORDS = (ContactPortalAccess, PortalLoginOtp)


def require_contact_merge_access(
    db: Session, actor: User, contact_ids: tuple[uuid.UUID, uuid.UUID], *, lock: bool = False,
) -> None:
    """Matter access is also the existing read permission for affected record types.

    On merge, lock contacts (blocking new FK references), existing references and
    their parents, then matters and ACL rows. Check fresh state in the same
    transaction as the merge. Preview is advisory and takes no write locks.
    """
    sqlite = db.get_bind().dialect.name == 'sqlite'

    def present(model):
        # Legacy unit fixtures intentionally create only a subset of the schema.
        return not sqlite or inspect(db.get_bind()).has_table(model.__tablename__)

    def rows(model, condition):
        stmt = select(model).where(condition).order_by(*model.__table__.primary_key.columns)
        if lock:
            stmt = stmt.with_for_update()
        return list(db.scalars(stmt.execution_options(populate_existing=True)))

    contacts = rows(Contact, Contact.id.in_(contact_ids))
    if len(contacts) != len(set(contact_ids)):
        raise HTTPException(404, 'Contact not found')
    # Refresh authorization state; do not reuse a previously loaded role/category.
    staff = rows(User, User.id == actor.id)
    if not staff or not staff[0].is_active:
        raise HTTPException(403, 'Active staff account required')
    actor = staff[0]
    if actor.permission_category_id and present(UserPermissionCategory):
        rows(UserPermissionCategory, UserPermissionCategory.id == actor.permission_category_id)

    case_ids = set()
    for model in DIRECT_MATTER_RECORDS:
        if present(model):
            case_ids.update(row.case_id for row in rows(model, model.contact_id.in_(contact_ids)))
    for model, foreign_key, parent in INDIRECT_MATTER_RECORDS:
        if not present(model):
            continue
        records = rows(model, model.contact_id.in_(contact_ids))
        parent_ids = {getattr(row, foreign_key) for row in records}
        if parent_ids:
            parents = rows(parent, parent.id.in_(parent_ids))
            if len(parents) != len(parent_ids):
                raise HTTPException(403, 'Cannot verify access to an affected record')
            case_ids.update(row.case_id for row in parents)
    for model in GLOBAL_RECORDS:
        if present(model):
            rows(model, model.contact_id.in_(contact_ids))
    if case_ids:
        matters = rows(Case, Case.id.in_(case_ids))
        if len(matters) != len(case_ids):
            raise HTTPException(403, 'Cannot verify access to an affected matter')
        if present(CaseAccessRule):
            rows(CaseAccessRule, CaseAccessRule.case_id.in_(case_ids))
        for case_id in sorted(case_ids, key=str):
            try:
                require_case_access(case_id, actor, db)
            except HTTPException as exc:
                # Do not disclose which inaccessible matter or record was found.
                raise HTTPException(403, 'Merge requires access to every affected matter and record') from exc

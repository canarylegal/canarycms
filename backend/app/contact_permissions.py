"""Authorization for credentials that span all of a contact's matters."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.deps import require_case_access
from app.models import (
    CaseContact, ContactPortalGrant, MatterPortalAccess, User,
    PortalFormSubmission, QuotePortalDelivery,
    CanarySignRequest, CanarySignRecipient,
    DocusignSigningRequest, DocusignSigningRecipient,
)


def require_contact_portal_access(db: Session, user: User, contact_id: uuid.UUID) -> None:
    """A global login requires access to every linked matter, including retained grants.

    Check inactive grants/access too: reactivation must not restore unauthorized access.
    Unlinked contacts remain available to staff under the global address-book policy.
    """
    if user_effective_admin(user, db):
        return
    case_ids = set()
    for model in (CaseContact, ContactPortalGrant, MatterPortalAccess, PortalFormSubmission, QuotePortalDelivery):
        case_ids.update(db.scalars(select(model.case_id).where(model.contact_id == contact_id)))
    for request, recipient in (
        (CanarySignRequest, CanarySignRecipient),
        (DocusignSigningRequest, DocusignSigningRecipient),
    ):
        case_ids.update(db.scalars(
            select(request.case_id)
            .join(recipient, recipient.signing_request_id == request.id)
            .where(recipient.contact_id == contact_id)
        ))
    for case_id in sorted(case_ids, key=str):
        require_case_access(case_id, user, db)

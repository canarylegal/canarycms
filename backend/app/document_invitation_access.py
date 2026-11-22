"""Document recipient identity and revocation checks, without provisioning login."""
import hashlib
import hmac
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models import CaseContact, Contact, ContactPortalAccess, PortalMatterBlock
from app.security import JWT_SECRET
from app.portal_service import portal_access_is_active


def recipient(db, case_id, contact_id=None, case_contact_id=None, *, lock=False):
    db.flush()
    stmt = select(CaseContact).where(CaseContact.case_id == case_id)
    if case_contact_id is not None:stmt = stmt.where(CaseContact.id == case_contact_id)
    elif contact_id is not None:stmt = stmt.where(CaseContact.contact_id == contact_id)
    else:raise HTTPException(400, 'Select a contact on this matter')
    if lock:stmt = stmt.with_for_update(read=True)
    cc = db.scalar(stmt.execution_options(populate_existing=True))
    if cc is None or cc.contact_id is None or (contact_id is not None and cc.contact_id != contact_id):
        raise HTTPException(400, 'Recipient must be the selected contact on this matter')
    contact_stmt = select(Contact).where(Contact.id == cc.contact_id)
    if lock:contact_stmt = contact_stmt.with_for_update(read=True)
    contact = db.scalar(contact_stmt.execution_options(populate_existing=True))
    if contact is None:raise HTTPException(400, 'Contact is unavailable')
    email = (cc.email or contact.email or '').strip().lower()
    if not email:raise HTTPException(400, 'Matter contact has no email address')
    if db.get(PortalMatterBlock, (case_id, contact.id)):
        raise HTTPException(403, 'Document access to this matter has been revoked')
    return cc, contact, email


def binding(db, case_id, contact_id, case_contact_id=None, *, lock=False):
    cc, contact, email = recipient(db, case_id, contact_id, case_contact_id, lock=lock)
    stmt = select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    if lock:stmt = stmt.with_for_update(read=True)
    access = db.scalar(stmt.execution_options(populate_existing=True))
    # Preserve revocation on existing portal resets without exposing a code hash in URLs.
    stamp = None
    if access:
        raw = json.dumps([str(access.id), access.session_version, access.enabled, access.code_sha256,
            str(access.expires_at)], default=str)
        stamp = hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return {'case_contact': str(cc.id), 'email': email, 'portal_stamp': stamp,
        'portal_active': bool(access and portal_access_is_active(access))}


def validate_binding(db, case_id, contact_id, expected, *, lock=False):
    import uuid
    current = binding(db, case_id, contact_id, uuid.UUID(expected['case_contact']), lock=lock)
    if current != expected:
        raise ValueError('Document recipient or access changed')
    return current

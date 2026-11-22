"""Document-only invitations; never create or enable a contact-wide portal login."""
import hashlib
import json
import time
import uuid
from datetime import timezone
from fastapi import HTTPException
from jose import jwt, JWTError
from sqlalchemy import select
from app.models import ContactPortalAccess, PortalFormSubmission, QuotePortalDelivery, CanarySignRecipient, CanarySignRequest, PortalMatterBlock
from app.security import JWT_SECRET, JWT_ALG, PORTAL_QUOTE_EXCHANGE_TTL_SECONDS
from app.portal_service import portal_access_is_active
from app.document_invitation_access import binding, validate_binding


def generation(row):
    if isinstance(row, CanarySignRecipient):return hashlib.sha256(row.sign_token.encode()).hexdigest()
    sent = row.sent_at
    if sent.tzinfo is None:sent = sent.replace(tzinfo=timezone.utc)
    return sent.isoformat()


def coordinates(db, kind, row):
    return (db.get(CanarySignRequest,row.signing_request_id).case_id if kind=='sign' else row.case_id), row.contact_id


def issue(db, kind, row):
    case_id, contact_id = coordinates(db,kind,row)
    if kind=='sign':
        if not row.document_invitation_binding:raise ValueError('Signing invitation needs a validated resend')
        authority=json.loads(row.document_invitation_binding)
        validate_binding(db,case_id,contact_id,authority)
    else:authority=binding(db,case_id,contact_id)
    now=int(time.time())
    return jwt.encode({'purpose':'portal_invitation','v':2,'kind':kind,'resource':str(row.id),
        'contact':str(contact_id),'case':str(case_id),'binding':authority,
        'generation':generation(row),'iat':now,'exp':now+PORTAL_QUOTE_EXCHANGE_TTL_SECONDS},JWT_SECRET,algorithm=JWT_ALG)


def resolve(db, token, kind, *, completed=False, lock=False):
    try:
        claims=jwt.decode(token,JWT_SECRET,algorithms=[JWT_ALG])
        if claims.get('purpose')!='portal_invitation' or claims.get('kind')!=kind:raise ValueError()
        model={'form':PortalFormSubmission,'quote':QuotePortalDelivery,'sign':CanarySignRecipient}[kind]
        stmt=select(model).where(model.id==uuid.UUID(claims['resource'])).execution_options(populate_existing=True)
        if lock and kind == 'sign':
            candidate=db.scalar(stmt)
            if candidate is None:raise ValueError()
            db.scalar(select(CanarySignRequest).where(CanarySignRequest.id==candidate.signing_request_id)
                .with_for_update().execution_options(populate_existing=True))
        if lock:stmt=stmt.with_for_update()
        row=db.scalar(stmt)
        if row is None:raise ValueError()
        case_id,contact_id=coordinates(db,kind,row)
        if claims['contact']!=str(contact_id) or claims['case']!=str(case_id) or claims['generation']!=generation(row):raise ValueError()
        if kind=='sign':
            req=db.get(CanarySignRequest,row.signing_request_id)
            expires=req.expires_at.replace(tzinfo=timezone.utc) if req.expires_at.tzinfo is None else req.expires_at
            if req.status.value not in (('pending','completed') if completed else ('pending',)):raise ValueError()
            if req.status.value=='pending' and expires.timestamp()<=time.time():raise ValueError()
            allowed=('pending','viewed','signed') if completed else ('pending','viewed')
            from app.portal_case import firm_canary_sign_enabled
            if not firm_canary_sign_enabled(db):raise ValueError()
            if not row.document_invitation_binding or json.loads(row.document_invitation_binding)!=claims.get('binding'):raise ValueError()
        else:
            allowed=('pending','completed') if completed and kind=='form' else ('pending','accepted','declined') if completed else ('pending',)
        if row.status.value not in allowed:raise ValueError()
        if claims.get('v')==2:
            validate_binding(db,case_id,contact_id,claims['binding'],lock=lock)
        else:
            # Already-issued form/quote links retain their original revocation checks.
            if kind=='sign':raise ValueError()
            access=db.scalar(select(ContactPortalAccess).where(ContactPortalAccess.contact_id==contact_id).execution_options(populate_existing=True))
            if access is None or not portal_access_is_active(access) or access.session_version!=claims['sv']:raise ValueError()
        if db.get(PortalMatterBlock,(case_id,contact_id)):raise ValueError()
        from app.portal_case import require_case_portal_enabled
        require_case_portal_enabled(db,case_id)
        return row
    except (JWTError,ValueError,KeyError,TypeError,AttributeError,HTTPException) as exc:
        raise ValueError('Invalid or expired document invitation; request a new link') from exc

"""Staff merges require access to all records on both sides, including history."""
import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

from app.main import app
from app.db import SessionLocal
from app.models import (
    Contact, ContactType, CaseContact, ContactPortalGrant, MatterPortalAccess,
    PortalActivityEvent, PortalMatterBlock, QuotePortalDelivery, PortalFormTemplate,
    PortalFormSubmission, CanarySignRequest, CanarySignRecipient,
    DocusignSigningRequest, DocusignSigningRecipient, LedgerEntry, LedgerAccount,
    LedgerAccountType, LedgerDirection, CaseInvoice, User, CaseAccessRule,
    AuditEvent, ContactPortalAccess,
)
from app.portal_grant_views import ContactPortalGrantView
from app.portal_service import store_matter_portal_access_code, generate_access_code
from app.contact_merge_permissions import require_contact_merge_access
from app.contact_merge_service import merge_contacts, preview_contact_merge
from app.timeutil import utcnow
from tests.test_permission_boundaries_postgres import sample, allow_staff

KINDS = ['matter_link', 'grant', 'matter_access', 'form', 'quote', 'canary_sign',
         'docusign', 'ledger', 'invoice', 'activity', 'block', 'grant_view']


def prepare(s, kind, side):
    """Leave exactly the selected record type as the link to the restricted case."""
    with SessionLocal() as db:
        source = uuid.UUID(s['contact'])
        db.execute(delete(CaseContact).where(CaseContact.contact_id == source))
        db.execute(delete(ContactPortalGrant).where(ContactPortalGrant.contact_id == source))
        survivor = Contact(type=ContactType.person, name='Synthetic survivor', email=uuid.uuid4().hex+'@example.com')
        db.add(survivor)
        db.flush()
        sid = survivor.id
        target = source if side == 'source' else sid
        cid, fid, uid = (uuid.UUID(s[k]) for k in ('case', 'file', 'admin'))
        if kind == 'matter_link':
            db.add(CaseContact(case_id=cid, contact_id=target, type=ContactType.person, name='Retained contact'))
        elif kind == 'grant':
            db.add(ContactPortalGrant(case_id=cid, contact_id=target, folder_path='Shared', created_by_user_id=uid, expires_at=utcnow()-timedelta(days=1)))
        elif kind == 'matter_access':
            row = MatterPortalAccess(case_id=cid, contact_id=target, enabled=False, created_by_user_id=uid)
            store_matter_portal_access_code(row, generate_access_code())
            db.add(row)
        elif kind == 'form':
            template = PortalFormTemplate(name='Synthetic form', reference=uuid.uuid4().hex, owner_id=uid)
            db.add(template)
            db.flush()
            db.add(PortalFormSubmission(case_id=cid, contact_id=target, template_id=template.id))
        elif kind == 'quote':
            db.add(QuotePortalDelivery(case_id=cid, contact_id=target, file_id=fid, file_version_at_send=1))
        elif kind in ('canary_sign', 'docusign'):
            req_model, rec_model = ((CanarySignRequest, CanarySignRecipient) if kind == 'canary_sign' else (DocusignSigningRequest, DocusignSigningRecipient))
            extra = {'expires_at': utcnow()+timedelta(days=1)} if kind == 'canary_sign' else {}
            req = req_model(case_id=cid, source_file_id=fid, **extra)
            db.add(req)
            db.flush()
            extra = {} if kind == 'canary_sign' else {'client_user_id': uuid.uuid4().hex}
            db.add(rec_model(signing_request_id=req.id, contact_id=target, name='Synthetic recipient', email='synthetic@example.com', sign_token=uuid.uuid4().hex, **extra))
        elif kind == 'ledger':
            account = db.scalar(select(LedgerAccount).where(LedgerAccount.case_id == cid, LedgerAccount.account_type == LedgerAccountType.client))
            if account is None:
                account = LedgerAccount(case_id=cid, account_type=LedgerAccountType.client)
                db.add(account)
                db.flush()
            db.add(LedgerEntry(account_id=account.id, pair_id=uuid.uuid4(), direction=LedgerDirection.credit, amount_pence=100, description='Synthetic retained leg', contact_id=target))
        elif kind == 'invoice':
            db.add(CaseInvoice(case_id=cid, contact_id=target, invoice_number=uuid.uuid4().hex, status='draft', total_pence=100))
        elif kind == 'activity':
            db.add(PortalActivityEvent(case_id=cid, contact_id=target, action='synthetic', summary='Retained event'))
        elif kind == 'block':
            db.add(PortalMatterBlock(case_id=cid, contact_id=target))
        elif kind == 'grant_view':
            other = Contact(type=ContactType.person, name='Synthetic grant owner')
            db.add(other)
            db.flush()
            grant = ContactPortalGrant(case_id=cid, contact_id=other.id, folder_path='Shared', created_by_user_id=uid)
            db.add(grant)
            db.flush()
            db.add(ContactPortalGrantView(contact_id=target, grant_id=grant.id, last_viewed_at=utcnow()))
        db.commit()
        return str(sid)


def snapshot():
    from app.contact_merge_permissions import DIRECT_MATTER_RECORDS, INDIRECT_MATTER_RECORDS, GLOBAL_RECORDS
    models = {Contact, *DIRECT_MATTER_RECORDS, *GLOBAL_RECORDS,
              *(model for model, _, _ in INDIRECT_MATTER_RECORDS)}
    with SessionLocal() as db:
        return {model.__tablename__: sorted(repr(tuple(row)) for row in db.execute(select(model.__table__))) for model in models}


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('side', ['source', 'survivor'])
def test_denied_preview_and_merge_leave_all_records_unchanged(sample, kind, side):
    s = sample
    sid = prepare(s, kind, side)
    before = snapshot()
    with TestClient(app) as c:
        response = c.get('/contacts/'+sid+'/merge-preview', params={'source_contact_id':s['contact']}, headers=s['headers'])
        assert response.status_code == 403, response.text
        assert s['case'] not in response.text
        response = c.post('/contacts/'+sid+'/merge', json={'source_contact_id':s['contact'], 'send_email':False}, headers=s['headers'])
        assert response.status_code == 403, response.text
    assert snapshot() == before
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'contact.merge', AuditEvent.entity_id == sid)) is None


@pytest.mark.parametrize('kind', KINDS)
def test_staff_with_access_can_merge_each_record_type(sample, kind):
    s = sample
    sid = prepare(s, kind, 'source')
    allow_staff(s)
    with TestClient(app) as c:
        preview = c.get('/contacts/'+sid+'/merge-preview', params={'source_contact_id':s['contact']}, headers=s['headers'])
        assert preview.status_code == 200, preview.text
        response = c.post('/contacts/'+sid+'/merge', json={'source_contact_id':s['contact'], 'send_email':False}, headers=s['headers'])
        assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.get(Contact, uuid.UUID(s['contact'])) is None
        assert db.get(Contact, uuid.UUID(sid)) is not None
        for model in (LedgerEntry, CaseInvoice):
            if (kind == 'ledger' and model is LedgerEntry) or (kind == 'invoice' and model is CaseInvoice):
                record = db.scalar(select(model).where(model.contact_id == uuid.UUID(sid)))
                assert record is not None
                assert (record.amount_pence if kind == 'ledger' else record.total_pence) == 100


def test_staff_can_merge_unlinked_contacts(sample):
    s = sample
    sid = prepare(s, 'none', 'source')
    with TestClient(app) as c:
        assert c.post('/contacts/'+sid+'/merge', json={'source_contact_id':s['contact'], 'send_email':False}, headers=s['headers']).status_code == 200


def test_revocation_after_preview_is_rechecked_even_with_cached_actor(sample):
    s = sample
    sid = prepare(s, 'ledger', 'survivor')
    allow_staff(s)
    with SessionLocal() as db:
        actor = db.get(User, uuid.UUID(s['staff']))
        preview_contact_merge(db, survivor_id=uuid.UUID(sid), source_id=uuid.UUID(s['contact']), actor=actor)
        with SessionLocal() as change:
            change.execute(delete(CaseAccessRule).where(CaseAccessRule.user_id == actor.id))
            change.commit()
        before = snapshot()
        with pytest.raises(HTTPException) as caught:
            merge_contacts(db, survivor_id=uuid.UUID(sid), source_id=uuid.UUID(s['contact']), actor=actor)
        assert caught.value.status_code == 403
        db.rollback()
    assert snapshot() == before


def test_new_restricted_record_after_preview_blocks_merge(sample):
    s = sample
    sid = prepare(s, 'none', 'source')
    with TestClient(app) as c:
        assert c.get('/contacts/'+sid+'/merge-preview', params={'source_contact_id':s['contact']}, headers=s['headers']).status_code == 200
        with SessionLocal() as db:
            db.add(PortalActivityEvent(case_id=uuid.UUID(s['case']), contact_id=uuid.UUID(sid), action='synthetic', summary='New restricted link'))
            db.commit()
        assert c.post('/contacts/'+sid+'/merge', json={'source_contact_id':s['contact'], 'send_email':False}, headers=s['headers']).status_code == 403


@pytest.mark.parametrize('change', ['new_reference', 'revoke_acl'])
def test_merge_transaction_locks_prevent_authorization_changes(sample, change):
    s = sample
    sid = prepare(s, 'matter_link', 'source')
    allow_staff(s)
    with SessionLocal() as db:
        actor = db.get(User, uuid.UUID(s['staff']))
        require_contact_merge_access(db, actor, (uuid.UUID(sid), uuid.UUID(s['contact'])), lock=True)
        with SessionLocal() as other:
            other.execute(text("SET LOCAL lock_timeout = '150ms'"))
            with pytest.raises(DBAPIError) as caught:
                if change == 'new_reference':
                    other.add(PortalActivityEvent(case_id=uuid.UUID(s['case']), contact_id=uuid.UUID(sid), action='synthetic', summary='Concurrent reference'))
                    other.flush()
                else:
                    other.execute(delete(CaseAccessRule).where(CaseAccessRule.user_id == actor.id))
            assert caught.value.orig.sqlstate == '55P03'
            other.rollback()
        db.rollback()


def test_every_contact_foreign_key_has_an_authorization_classification():
    from app.models import Base
    from app.contact_merge_permissions import DIRECT_MATTER_RECORDS, INDIRECT_MATTER_RECORDS, GLOBAL_RECORDS
    expected = {model.__tablename__ for model in (*DIRECT_MATTER_RECORDS, *GLOBAL_RECORDS)}
    expected.update(model.__tablename__ for model, _, _ in INDIRECT_MATTER_RECORDS)
    actual = {table.name for table in Base.metadata.tables.values() for fk in table.foreign_keys if fk.target_fullname == 'contact.id'}
    assert actual == expected

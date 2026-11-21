"""Invitation, preview and revocation regressions against isolated PostgreSQL."""
import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import (QuotePortalDelivery,QuotePortalDeliveryStatus,PortalFormSubmission,PortalFormSubmissionStatus,ContactPortalAccess,User,UserRole,Case,CaseLockMode,PortalMatterBlock,ContactPortalGrant,CaseContact,ContactType,UserPermissionCategory)
from app.security import create_access_token, create_portal_quote_exchange_token
from app.timeutil import utcnow
from tests.conftest import db
from tests.test_portal_access_postgres import safe,data,headers,url,get,revoke

@pytest.fixture
def links(data):
    with SessionLocal() as db:
        quote=QuotePortalDelivery(id=uuid.uuid4(),case_id=data['cid'],contact_id=data['contact'],file_id=data['file'],file_version_at_send=1,sent_by_user_id=data['uid'])
        from app.models import File
        quote.file_version_at_send=db.get(File,data['file']).version or 1
        db.add(quote);db.commit();data['quote']=quote.id
        data['legacy_quote']=create_portal_quote_exchange_token(contact_id=str(data['contact']),case_id=str(data['cid']),file_id=str(data['file']),delivery_id=str(quote.id))
        from app.portal_invitation import issue
        data['form_link']=issue(db, 'form', db.get(PortalFormSubmission,data['sub']))
        data['quote_link']=issue(db, 'quote', quote)
    return data

def exchange(d,kind):
    token=d['form_link'] if kind=='form' else d['legacy_quote'] if kind=='quote_jwt' else d['quote_link']
    return d['client'].post('/portal/'+('form' if kind=='form' else 'quote')+'-exchange',json={'exchange_token':token})
def bearer(response): return {'Authorization':'Bearer '+response.json()['session_token']}

@pytest.mark.parametrize('kind',['form','quote','quote_jwt'])
def test_link_does_not_grant_unrelated_documents(links,kind):
    r=exchange(links,kind)
    if kind=='quote_jwt':
        assert r.status_code==401;return
    assert r.status_code==200,r.text
    result=links['client'].get(url(links,'file'),headers=bearer(r))
    assert result.status_code in (401,403,404),f'{kind}: unrelated download HTTP {result.status_code}'

@pytest.mark.parametrize('kind',['form','quote','quote_jwt'])
def test_rotation_invalidates_old_link(links,kind):
    revoke(links,'version');assert get(links,'file').status_code==401
    r=exchange(links,kind)
    assert r.status_code in (401,403,404),f'{kind}: old link minted fresh session HTTP {r.status_code}'

@pytest.mark.parametrize('kind',['form','quote','quote_jwt'])
@pytest.mark.parametrize('mode',['disabled','expired','matter','firm'])
def test_disabled_access_blocks_link(links,kind,mode):
    revoke(links,mode)
    assert exchange(links,kind).status_code in (401,403,404)

@pytest.mark.parametrize('kind',['form','quote'])
def test_old_link_expiry_is_enforced(links,kind):
    with SessionLocal() as db:
        row=db.get(PortalFormSubmission,links['sub']) if kind=='form' else db.get(QuotePortalDelivery,links['quote'])
        row.sent_at=utcnow()-timedelta(days=366);db.commit()
    assert exchange(links,kind).status_code==401

@pytest.mark.parametrize('state',['accepted','declined','superseded'])
def test_inactive_quote_link_cannot_login(links,state):
    with SessionLocal() as db:
        db.get(QuotePortalDelivery,links['quote']).status=QuotePortalDeliveryStatus(state);db.commit()
    r=exchange(links,'quote')
    assert r.status_code in (401,403,404),f'{state}: HTTP {r.status_code}'

@pytest.mark.parametrize('state',['completed','voided','superseded'])
def test_inactive_form_link_rejected(links,state):
    with SessionLocal() as db:
        db.get(PortalFormSubmission,links['sub']).status=PortalFormSubmissionStatus(state);db.commit()
    assert exchange(links,'form').status_code==401

@pytest.mark.parametrize('kind',['form','quote'])
def test_matter_contact_revocation_blocks_link_exchange(links,kind):
    with SessionLocal() as db:
        db.add(PortalMatterBlock(case_id=links['cid'],contact_id=links['contact']));db.commit()
    r=exchange(links,kind)
    assert r.status_code in (401,403,404),f'{kind}: revoked matter link still minted session HTTP {r.status_code}'

@pytest.fixture
def preview(links):
    from tests.ledger_test_helpers import add_user, add_fee_earner_category
    with SessionLocal() as db:
        staff=db.get(User,links['uid']);staff.role=UserRole.user;staff.permission_category_id=db.scalar(select(UserPermissionCategory.id).where(UserPermissionCategory.name=="Fee earner"))
        db.add(CaseContact(case_id=links['cid'],contact_id=links['contact'],type=ContactType.person,name='Synthetic client',matter_contact_type='client'))
        outsider=add_user(db)
        case=db.get(Case,links['other_case']);case.fee_earner_user_id=outsider.id;case.lock_mode=CaseLockMode.allow_list
        db.commit()
        token=create_access_token(user_id=str(staff.id),role=staff.role.value,auth_token_version=staff.auth_token_version)
    links['staff_token']=token
    r=links['client'].post(f"/cases/{links['cid']}/portal/preview",headers={'Authorization':'Bearer '+token},json={'contact_id':str(links['contact'])})
    assert r.status_code==200,r.text
    links['preview_link']=r.json()['exchange_token']
    return links

def preview_exchange(d):
    return d['client'].post('/portal/auth/preview-exchange',json={'exchange_token':d['preview_link']})
def remove_staff(d,mode):
    with SessionLocal() as db:
        user=db.get(User,d['uid'])
        if mode=='disabled':user.is_active=False
        else:
            from tests.ledger_test_helpers import add_user
            other=add_user(db)
            case=db.get(Case,d['cid']);case.fee_earner_user_id=other.id;case.lock_mode=CaseLockMode.allow_list
        db.commit()

@pytest.mark.parametrize('mode',['disabled','matter_permission'])
def test_preview_link_rechecks_staff_authority(preview,mode):
    remove_staff(preview,mode)
    r=preview_exchange(preview)
    assert r.status_code in (401,403,404),f'{mode}: preview exchange HTTP {r.status_code}'

@pytest.mark.parametrize('mode',['disabled','matter_permission'])
def test_preview_session_rechecks_staff_authority(preview,mode):
    r=preview_exchange(preview);assert r.status_code==200
    remove_staff(preview,mode)
    result=preview['client'].get(url(preview,'file'),headers=bearer(r))
    assert result.status_code in (401,403,404),f'{mode}: existing preview still downloads HTTP {result.status_code}'

def test_preview_cannot_read_staff_inaccessible_matter(preview):
    from app import canary_sign_service as sign
    with SessionLocal() as db:
        file=sign._save_case_file(db,case_id=preview['other_case'],owner_id=preview['uid'],folder_path='Shared',filename='other.txt',mime_type='text/plain',raw=b'other synthetic matter')
        grant=ContactPortalGrant(contact_id=preview['contact'],case_id=preview['other_case'],folder_path='Shared',created_by_user_id=preview['uid'])
        db.add(grant);db.commit();fid=file.id;gid=grant.id
    denied=preview['client'].post(f"/cases/{preview['other_case']}/portal/preview",headers={'Authorization':'Bearer '+preview['staff_token']},json={'contact_id':str(preview['contact'])})
    assert denied.status_code==403
    r=preview_exchange(preview);assert r.status_code==200
    result=preview['client'].get(f'/portal/grants/{gid}/files/{fid}',headers=bearer(r))
    assert result.status_code in (401,403,404),f'direct staff preview denied, other-matter download HTTP {result.status_code}'

@pytest.mark.parametrize('kind',['form','quote'])
def test_preview_cannot_upgrade_to_client_write_via_visible_id(preview,kind):
    r=preview_exchange(preview);assert r.status_code==200
    path=f"/portal/forms/{preview['sub']}/submit"
    blocked=preview['client'].post(path,headers=bearer(r),json={'responses':{}})
    assert blocked.status_code==403
    # IDs are exposed by the legitimate preview list; no inbox link or client code needed.
    listing=preview['client'].get('/portal/forms' if kind=='form' else '/portal/quote-deliveries',headers=bearer(r))
    assert listing.status_code==200
    identity=str(preview['sub'] if kind=='form' else preview['quote'])
    assert any(x['id']==identity for x in listing.json())
    upgraded=preview['client'].post('/portal/'+kind+'-exchange',json={'exchange_token':identity})
    if upgraded.status_code!=200:
        assert upgraded.status_code in (401,403,404);return
    result=preview['client'].post(path,headers=bearer(upgraded),json={'responses':{}})
    with SessionLocal() as db: persisted=db.get(PortalFormSubmission,preview['sub']).status.value
    assert result.status_code in (401,403,404),f'{kind} ID removed read-only restriction: HTTP {result.status_code}, persisted {persisted}'

@pytest.mark.parametrize('kind',['form','quote'])
def test_invalid_link_rejected(links,kind):
    response=links['client'].post('/portal/'+kind+'-exchange',json={'exchange_token':str(uuid.uuid4())})
    assert response.status_code==401


@pytest.mark.parametrize('kind',['read','submit'])
def test_expired_client_session_blocks_form_and_preserves_data(links,kind):
    from jose import jwt
    from app.security import JWT_SECRET,JWT_ALG
    claims=jwt.get_unverified_claims(links['token']);claims['exp']=1
    token=jwt.encode(claims,JWT_SECRET,algorithm=JWT_ALG)
    path=f"/portal/forms/{links['sub']}"
    h={'Authorization':'Bearer '+token}
    r=links['client'].get(path,headers=h) if kind=='read' else links['client'].post(path+'/submit',headers=h,json={'responses':{}})
    assert r.status_code==401
    with SessionLocal() as db:
        sub=db.get(PortalFormSubmission,links['sub'])
        assert sub.status.value=='pending' and sub.snapshot_file_id is None


def test_expired_preview_exchange_rejected(preview):
    from jose import jwt
    from app.security import JWT_SECRET,JWT_ALG
    claims=jwt.get_unverified_claims(preview['preview_link']);claims['exp']=1
    preview['preview_link']=jwt.encode(claims,JWT_SECRET,algorithm=JWT_ALG)
    assert preview_exchange(preview).status_code==401

@pytest.mark.parametrize('kind',['form','quote'])
def test_revoked_matter_link_cannot_unlock_other_matter(links,kind):
    from app import canary_sign_service as sign
    with SessionLocal() as db:
        file=sign._save_case_file(db,case_id=links['other_case'],owner_id=links['uid'],folder_path='Shared',filename='other.txt',mime_type='text/plain',raw=b'synthetic other matter')
        grant=ContactPortalGrant(contact_id=links['contact'],case_id=links['other_case'],folder_path='Shared',created_by_user_id=links['uid'])
        db.add(grant);db.add(PortalMatterBlock(case_id=links['cid'],contact_id=links['contact']));db.commit();fid=file.id;gid=grant.id
    r=exchange(links,kind)
    if r.status_code!=200:
        assert r.status_code in (401,403,404);return
    assert links['client'].get(url(links,'file'),headers=bearer(r)).status_code==403
    response=links['client'].get(f'/portal/grants/{gid}/files/{fid}',headers=bearer(r))
    assert response.status_code in (401,403,404),f'revoked source blocked but fresh general session reads other matter HTTP {response.status_code}'


def test_preview_contact_revocation_is_enforced(preview):
    r=preview_exchange(preview);assert r.status_code==200
    revoke(preview,'disabled')
    assert preview['client'].get(url(preview,'file'),headers=bearer(r)).status_code==401
    assert preview_exchange(preview).status_code==403

@pytest.mark.parametrize('kind', ['form', 'quote'])
def test_resource_id_is_never_login(links, kind):
    identity = links['sub'] if kind == 'form' else links['quote']
    assert links['client'].post('/portal/'+kind+'-exchange', json={'exchange_token':str(identity)}).status_code == 401

@pytest.mark.parametrize('kind', ['form', 'quote'])
def test_invitation_session_lists_only_its_resource(links, kind):
    response=exchange(links,kind); assert response.status_code == 200,response.text
    h=bearer(response)
    session=links['client'].get('/portal/session',headers=h)
    assert session.status_code == 200,session.text
    assert session.json()['contact_id']==str(links['contact'])
    assert session.json()['grants']==[]
    forms=links['client'].get('/portal/forms',headers=h)
    quotes=links['client'].get('/portal/quote-deliveries',headers=h)
    assert forms.status_code==quotes.status_code==200
    assert [x['id'] for x in forms.json()]==([str(links['sub'])] if kind=='form' else [])
    assert [x['id'] for x in quotes.json()]==([str(links['quote'])] if kind=='quote' else [])
    actions=links['client'].get('/portal/client-actions',headers=h)
    assert actions.status_code==200,actions.text
    assert all(x['kind']==kind for group in actions.json().values() for x in group)
    assert links['client'].get(url(links,'file'),headers=h).status_code==403


def test_form_invitation_can_complete_only_intended_form(links):
    h=bearer(exchange(links,'form'))
    path=f"/portal/forms/{links['sub']}"
    assert links['client'].get(path,headers=h).status_code==200
    result=links['client'].post(path+'/submit',headers=h,json={'responses':{}})
    assert result.status_code==200,result.text
    assert links['client'].get(path,headers=h).json()['status']=='completed'
    assert exchange(links,'form').status_code==401

@pytest.mark.parametrize('kind', ['form','quote'])
@pytest.mark.parametrize('change',['rotation','resend','block'])
def test_existing_invitation_session_revalidates_current_authority(links,kind,change):
    h=bearer(exchange(links,kind))
    with SessionLocal() as db:
        if change=='rotation':
            access=db.scalar(select(ContactPortalAccess).where(ContactPortalAccess.contact_id==links['contact']))
            access.session_version+=1
        elif change=='block':db.add(PortalMatterBlock(case_id=links['cid'],contact_id=links['contact']))
        else:
            row=db.get(PortalFormSubmission,links['sub']) if kind=='form' else db.get(QuotePortalDelivery,links['quote'])
            row.sent_at=utcnow()
        db.commit()
    assert links['client'].get('/portal/session',headers=h).status_code in (401,403)


def test_quote_invitation_cannot_submit_form(links):
    h=bearer(exchange(links,'quote'))
    assert links['client'].post(f"/portal/forms/{links['sub']}/submit",headers=h,json={'responses':{}}).status_code==403


def test_preview_file_open_token_rechecks_staff(preview):
    h=bearer(preview_exchange(preview))
    response=preview['client'].post(url(preview,'file')+'/open-token',headers=h)
    assert response.status_code==200,response.text
    token=response.json()['token']
    assert preview['client'].get(url(preview,'file')+'/open',params={'token':token}).status_code==200
    remove_staff(preview,'disabled')
    response=preview['client'].get(url(preview,'file')+'/open',params={'token':token})
    assert response.status_code in (401,403,404)


def test_preview_staff_session_rotation_revokes_link_and_session(preview):
    h=bearer(preview_exchange(preview))
    with SessionLocal() as db:
        db.get(User,preview['uid']).auth_token_version+=1;db.commit()
    assert preview_exchange(preview).status_code==401
    assert preview['client'].get('/portal/session',headers=h).status_code==401


def test_quote_invitation_can_read_and_respond(links, monkeypatch):
    monkeypatch.setattr('app.quote_portal_service._notify_staff_quote_response', lambda *a, **k: None)
    h=bearer(exchange(links,'quote'))
    path=f"/portal/quote-deliveries/{links['quote']}"
    assert links['client'].get(path,headers=h).status_code==200
    assert links['client'].get(path+'/file',headers=h).status_code==200
    response=links['client'].post(path+'/respond',headers=h,json={'accepted':True})
    assert response.status_code==200,response.text
    assert response.json()['status']=='accepted'
    assert links['client'].get(path,headers=h).status_code==200
    assert exchange(links,'quote').status_code==401

@pytest.mark.parametrize('kind',['form','quote'])
def test_new_invitation_after_rotation_works_and_old_one_stays_revoked(links,kind):
    from app.portal_invitation import issue
    revoke(links,'version')
    assert exchange(links,kind).status_code==401
    with SessionLocal() as db:
        row=db.get(PortalFormSubmission,links['sub']) if kind=='form' else db.get(QuotePortalDelivery,links['quote'])
        new=issue(db,kind,row)
    response=links['client'].post('/portal/'+kind+'-exchange',json={'exchange_token':new})
    assert response.status_code==200,response.text
    assert links['client'].get('/portal/session',headers=bearer(response)).status_code==200
    assert exchange(links,kind).status_code==401


def test_legacy_unbound_preview_session_is_rejected(links):
    from app.security import create_portal_session_token
    token=create_portal_session_token(contact_id=str(links['contact']),staff_preview=True)
    assert links['client'].get('/portal/session',headers={'Authorization':'Bearer '+token}).status_code==401

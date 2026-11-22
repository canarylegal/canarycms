import uuid
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.db import SessionLocal
from app.models import CaseEvent, UserCalendarShare
from app.event_service import update_case_event, enrich_caldav_events_with_linked_case_events, _event_out
from app.schemas import CaseEventUpdate
from app.radicale_calendar import href_to_ref
from tests.ledger_test_helpers import add_user, add_case
from tests.test_calendar_access import _calendar

@pytest.fixture
def fixture(db,monkeypatch):
    owner=add_user(db,email=uuid.uuid4().hex+'@example.test');owner.caldav_password_enc='synthetic'
    staff=add_user(db,email=uuid.uuid4().hex+'@example.test')
    calendar=_calendar(db,owner)
    case=add_case(db,fee_earner_user_id=staff.id)
    event=CaseEvent(case_id=case.id,name='Matter title',event_date=date(2026,11,22),track_in_calendar=True)
    db.add(event);db.commit()
    ref=href_to_ref(f'http://radicale:5232/{owner.id}/{calendar.radicale_slug}/synthetic.ics')
    calls=[]
    def load(*args):calls.append(args);return object()
    monkeypatch.setattr('app.calendar_matter_links.load_event_on_principal',load)
    monkeypatch.setattr('app.event_service.map_cases_if_accessible',lambda db,user,ids:{case.id:case})
    return owner,staff,calendar,event,ref,calls


def link(db,event,actor,ref):
    return update_case_event(event.case_id,event.id,CaseEventUpdate(calendar_event_uid=ref),db,actor_user_id=actor.id)


@pytest.mark.parametrize('permission',[None,'read','public'])
def test_matter_access_does_not_grant_link_rights(db,fixture,permission):
    owner,staff,calendar,event,ref,calls=fixture
    if permission=='read':db.add(UserCalendarShare(calendar_id=calendar.id,grantee_user_id=staff.id,can_write=False))
    if permission=='public':calendar.is_public=True
    db.commit()
    with pytest.raises(HTTPException) as error:link(db,event,staff,ref)
    assert error.value.status_code==403
    db.rollback();db.refresh(event)
    assert event.calendar_event_uid is None and not calls


@pytest.mark.parametrize('writer',['owner','shared'])
def test_valid_link_keeps_calendar_title_and_allows_unlink(db,fixture,writer):
    owner,staff,calendar,event,ref,calls=fixture
    if writer=='shared':db.add(UserCalendarShare(calendar_id=calendar.id,grantee_user_id=staff.id,can_write=True));db.commit()
    actor=owner if writer=='owner' else staff
    result=link(db,event,actor,ref);db.commit()
    assert result.calendar_event_uid==ref and event.calendar_link_verified and len(calls)==1
    rows=[{'id':ref,'title':'Original personal appointment'}]
    enrich_caldav_events_with_linked_case_events(db,owner,rows)
    assert rows[0]['title']=='Original personal appointment'
    assert rows[0]['case_event_id']==str(event.id)
    result=link(db,event,staff,None);db.commit()
    assert result.calendar_event_uid is None and not event.calendar_link_verified


def test_historical_unverified_link_cannot_change_title_or_metadata(db,fixture):
    owner,staff,calendar,event,ref,calls=fixture
    event.calendar_event_uid=ref;db.commit()
    assert not event.calendar_link_verified and _event_out(event).calendar_event_uid is None
    assert _event_out(event).calendar_link_needs_review
    rows=[{'id':ref,'title':'Private appointment'}]
    enrich_caldav_events_with_linked_case_events(db,owner,rows)
    assert rows==[{'id':ref,'title':'Private appointment'}]
    with pytest.raises(HTTPException):link(db,event,staff,ref)
    db.rollback()
    link(db,event,owner,ref);db.commit();assert event.calendar_link_verified


@pytest.mark.parametrize('raw',['garbage','http://attacker.test/anything','http://radicale:5232/../x/y','http://radicale:5232/a/b/c?target=other','http://radicale:5232/a/b/%2Fsecret'])
def test_invalid_locations_rejected_without_network(db,fixture,raw):
    owner,staff,calendar,event,ref,calls=fixture
    with pytest.raises(HTTPException) as error:link(db,event,owner,raw if raw=='garbage' else href_to_ref(raw))
    assert error.value.status_code==400 and not calls


def test_missing_remote_event_cannot_be_linked(db,fixture,monkeypatch):
    owner,staff,calendar,event,ref,calls=fixture
    def missing(*_):raise HTTPException(404,'Event not found')
    monkeypatch.setattr('app.calendar_matter_links.load_event_on_principal',missing)
    with pytest.raises(HTTPException) as error:link(db,event,owner,ref)
    assert error.value.status_code==404
    db.rollback();db.refresh(event);assert not event.calendar_link_verified


def test_revoked_share_cannot_rebind(db,fixture):
    owner,staff,calendar,event,ref,calls=fixture
    share=UserCalendarShare(calendar_id=calendar.id,grantee_user_id=staff.id,can_write=True);db.add(share);db.commit()
    link(db,event,staff,ref);db.commit();db.delete(share);db.commit()
    with pytest.raises(HTTPException) as error:link(db,event,staff,ref)
    assert error.value.status_code==403


def test_concurrent_duplicate_links_only_one_wins(db,fixture):
    owner,staff,calendar,event,ref,calls=fixture
    other=CaseEvent(case_id=event.case_id,name='Other matter event',track_in_calendar=True)
    db.add(other);db.commit();ids=[event.id,other.id];owner_id=owner.id;case_id=event.case_id;barrier=Barrier(2)
    def bind(event_id):
        with SessionLocal() as session:
            barrier.wait(timeout=10)
            try:
                update_case_event(case_id,event_id,CaseEventUpdate(calendar_event_uid=ref),session,actor_user_id=owner_id)
                session.commit();return 200
            except HTTPException as error:session.rollback();return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(bind,ids))==[200,409]
    assert len(db.scalars(select(CaseEvent).where(CaseEvent.calendar_link_verified.is_(True),CaseEvent.calendar_event_uid==ref)).all())==1

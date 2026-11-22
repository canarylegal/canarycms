"""Run only in a disposable, migrated PostgreSQL database; jobs stay disabled."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from sqlalchemy import delete, select, func
from app.db import SessionLocal
from app.models import User, Case
from app.models.commercial_connection import CommercialConnection, CommercialCredential, CommercialOperation, CommercialApplication
from app import commercial_connection as c
from app.commercial_transport import ConnectionError
from tests.ledger_test_helpers import add_user, add_case
from tests.test_commercial_connection import FakeService


@pytest.fixture
def setup(db,monkeypatch):
    if db.bind.dialect.name!='postgresql' or os.getenv('COMMERCIAL_FOUNDATION_TEST')!='1':
        pytest.skip('Explicit isolated PostgreSQL required')
    for model in [CommercialApplication,CommercialOperation,CommercialCredential,CommercialConnection]:db.execute(delete(model))
    actor=add_user(db);case=add_case(db,fee_earner_user_id=actor.id);db.commit()
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ENABLED','1')
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ORIGIN','https://commercial.example.test')
    monkeypatch.setattr(c,'Transport',FakeService)
    FakeService.calls,FakeService.replies,FakeService.fail,FakeService.tamper=[],{},False,None
    def validate(x):
        if set(x)!={'reference'}:raise ValueError()
        return x
    def apply(session,op,result):
        matter=session.get(Case,op.case_id);matter.title += ' applied'
    monkeypatch.setattr(c,'ADAPTERS',{'synthetic.v1':c.Adapter('synthetic',validate,validate,apply)})
    c.activate(db,actor,'synthetic',0);c.set_credential(db,actor,'synthetic',{'password':'synthetic'},0)
    op=c.prepare(db,actor,case.id,'synthetic.v1',uuid.uuid4(),{'reference':'synthetic'})
    ids=(actor.id,case.id,op.id);db.rollback()
    yield ids


def test_parallel_dispatch_claim_survives_separate_sessions(setup,monkeypatch):
    actor,case,op=setup
    entered,contended=Event(),Event();original=FakeService.request
    def held(self,method,path,body=None,secret=None):
        if method=='POST' and '/operations/' in path:
            entered.set();assert contended.wait(10)
        return original(self,method,path,body,secret)
    monkeypatch.setattr(FakeService,'request',held)
    def send():
        with SessionLocal() as db:return c.exchange(db,db.get(User,actor),op).state
    def competing():
        assert entered.wait(10)
        try:
            with SessionLocal() as db:
                with pytest.raises(ConnectionError,match='reconciliation_required'):c.exchange(db,db.get(User,actor),op)
        finally:contended.set()
    with ThreadPoolExecutor(2) as pool:
        first,second=pool.submit(send),pool.submit(competing)
        assert first.result(15)=='completed';second.result(15)
    assert len([x for x in FakeService.calls if '/operations/' in x[1] and x[0]=='POST'])==1


def test_parallel_application_has_one_receipt_and_one_effect(setup):
    actor,case,op=setup
    with SessionLocal() as db:
        c.exchange(db,db.get(User,actor),op)
        before=db.get(Case,case).title
    def apply():
        with SessionLocal() as db:return c.apply_result(db,db.get(User,actor),op).state
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _:apply(),range(2)))==['applied','applied']
    with SessionLocal() as db:
        assert db.get(Case,case).title==before+' applied'
        assert db.scalar(select(func.count()).select_from(CommercialApplication))==1


def test_competing_credential_updates_reject_stale_version(setup):
    actor,case,op=setup
    def save(value):
        with SessionLocal() as db:
            try:c.set_credential(db,db.get(User,actor),'synthetic',{'password':value},1);return 'saved'
            except ConnectionError as e:return e.code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(save,['one','two']))==['saved','version_conflict']


def test_real_matter_access_denied_after_preparation(setup):
    from fastapi import HTTPException
    from app.models import UserRole
    actor,case,op=setup
    with SessionLocal() as db:
        denied=add_user(db,role=UserRole.user);db.commit()
        # Restrict to named fee earner rather than the firm's default permissive policy.
        from app.models import CaseLockMode
        matter=db.get(Case,case);matter.lock_mode=CaseLockMode.allow_list;db.commit()
        with pytest.raises(HTTPException):c.exchange(db,denied,op)

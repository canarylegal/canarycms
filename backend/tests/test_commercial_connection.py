"""Synthetic service only. No provider accounts, keys, credentials or network."""
import json
import uuid
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select, Table, Column, Integer, MetaData, func
from sqlalchemy.orm import Session
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app import commercial_connection as c
from app import commercial_transport as t
from app.models.commercial_connection import CommercialConnection, CommercialCredential, CommercialOperation, CommercialApplication

TABLES = [x.__table__ for x in (CommercialConnection, CommercialCredential, CommercialOperation, CommercialApplication)]


class FakeService:
    tenant = uuid.uuid4()
    calls = []
    replies = {}
    fail = False
    tamper = None

    def __init__(self, origin):
        assert origin == 'https://commercial.example.test'

    def request(self, method, path, body=None, secret=None):
        self.calls.append((method, path, body))
        if path.endswith('/activate'):
            return {'contract_version': '1', 'tenant_id': str(self.tenant),
                    'installation_id': body['installation_id'], 'installation_secret': 'synthetic-installation-secret-123456789'}
        if method == 'POST':
            response = {k: body[k] for k in ['contract_version', 'installation_id', 'tenant_id', 'operation_id', 'fingerprint']}
            response.update(state='completed', result={'reference': 'synthetic-receipt'})
            self.replies[path] = response
        if self.fail:
            raise t.ConnectionError('service_unavailable')
        data = dict(self.replies[path])
        if self.tamper:
            data.update(self.tamper)
        return data


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path/'local.db'))
    for table in TABLES: table.create(engine)
    metadata = MetaData()
    effects = Table('synthetic_effect', metadata, Column('id', Integer, primary_key=True))
    metadata.create_all(engine)
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ENABLED', '1')
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ORIGIN', 'https://commercial.example.test')
    monkeypatch.setattr(c, 'Transport', FakeService)
    monkeypatch.setattr(c, 'audit', lambda *args: None)
    actor = SimpleNamespace(id=uuid.uuid4())
    case = uuid.uuid4()
    def access(cid, user, db):
        if cid != case or user.id != actor.id: raise HTTPException(403)
    monkeypatch.setattr(c, 'require_case_access', access)
    def validate(payload):
        if set(payload) != {'reference'} or not isinstance(payload['reference'], str): raise ValueError('invalid')
        return payload
    def apply(db, op, result): db.execute(effects.insert().values(id=1))
    monkeypatch.setattr(c, 'ADAPTERS', {'synthetic.v1': c.Adapter('synthetic', validate, validate, apply)})
    FakeService.calls, FakeService.replies, FakeService.fail, FakeService.tamper = [], {}, False, None
    db = Session(engine)
    c.activate(db, actor, 'synthetic-code', 0)
    c.set_credential(db, actor, 'synthetic', {'password': 'synthetic-password'}, 0)
    yield SimpleNamespace(db=db, actor=actor, case=case, engine=engine, effects=effects)
    db.close(); engine.dispose()


def prepare(e, op_id=None):
    return c.prepare(e.db, e.actor, e.case, 'synthetic.v1', op_id or uuid.uuid4(), {'reference': 'synthetic-input'})


def test_default_disabled_and_required_encryption(env, monkeypatch):
    monkeypatch.delenv('CANARY_COMMERCIAL_SERVICE_ENABLED')
    with pytest.raises(t.ConnectionError, match='disabled'): prepare(env)
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ENABLED','1')
    monkeypatch.delenv('DATA_ENCRYPTION_KEY')
    with pytest.raises(t.ConnectionError, match='local_encryption_required'):
        c.set_credential(env.db, env.actor, 'synthetic', {'password':'new'}, 1)


@pytest.mark.parametrize('origin', ['http://bad.test','https://u:p@bad.test','https://bad.test/path','https://bad.test?q=1','https://bad.test#x','https://bad.test:80','https://bad.test:invalid'])
def test_origin_rejects_unsafe_configuration(env, monkeypatch, origin):
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ORIGIN',origin)
    with pytest.raises(t.ConnectionError, match='invalid_service_origin'): prepare(env)


def test_no_secret_in_metadata_or_operation_record(env):
    op=prepare(env)
    c.exchange(env.db,env.actor,op.id)
    env.db.expire_all()
    cred=env.db.get(CommercialCredential,'synthetic')
    assert 'synthetic-password' not in cred.secret_enc
    assert c.decrypt_password(cred.secret_enc)==json.dumps({'password':'synthetic-password'},sort_keys=True,separators=(',',':'))
    assert 'password' not in json.dumps(c.credential_status(env.db,'synthetic'))
    row=env.db.get(CommercialOperation,op.id)
    assert 'synthetic-password' not in repr(row.__dict__)
    assert 'synthetic-input' not in row.payload_enc
    assert 'synthetic-receipt' not in row.result_enc


@pytest.mark.parametrize('key', ['', ' ', '\t\n'])
def test_blank_dedicated_key_cannot_fall_back_to_jwt(env, monkeypatch, key):
    monkeypatch.setenv('DATA_ENCRYPTION_KEY', key)
    with pytest.raises(t.ConnectionError, match='local_encryption_required'):
        c.set_credential(env.db, env.actor, 'synthetic', {'password': 'synthetic'}, 1)


def test_updated_credential_used_at_dispatch_not_queue_time(env):
    op=prepare(env)
    c.set_credential(env.db,env.actor,'synthetic',{'password':'updated'},1)
    c.exchange(env.db,env.actor,op.id)
    assert FakeService.calls[-1][2]['credentials']=={'password':'updated'}
    assert FakeService.calls[-1][2]['credential_version']==2
    with pytest.raises(t.ConnectionError,match='version_conflict'):
        c.set_credential(env.db,env.actor,'synthetic',{'password':'stale'},1)
    env.db.rollback()
    assert json.loads(c.decrypt_password(env.db.get(CommercialCredential,'synthetic').secret_enc))=={'password':'updated'}


def test_revocation_is_versioned_and_blocks_queued_dispatch(env):
    op=prepare(env)
    c.set_credential(env.db,env.actor,'synthetic',None,1)
    with pytest.raises(t.ConnectionError,match='credential_required'):c.exchange(env.db,env.actor,op.id)
    env.db.rollback()
    assert c.credential_status(env.db,'synthetic')=={'key':'synthetic','version':2,'configured':False}
    with pytest.raises(t.ConnectionError,match='version_conflict'):c.set_credential(env.db,env.actor,'synthetic',{'password':'stale'},1)


def test_replay_binding_access_and_no_duplicate_submission(env):
    op=prepare(env)
    assert prepare(env,op.id).id==op.id
    with pytest.raises(t.ConnectionError,match='operation_conflict'):
        c.prepare(env.db,env.actor,env.case,'synthetic.v1',op.id,{'reference':'different'})
    env.db.rollback()
    with pytest.raises(HTTPException):c.exchange(env.db,SimpleNamespace(id=uuid.uuid4()),op.id)
    env.db.rollback()
    c.exchange(env.db,env.actor,op.id)
    c.exchange(env.db,env.actor,op.id)
    assert len([x for x in FakeService.calls if x[0]=='POST' and '/operations/' in x[1]])==1


def test_lost_response_requires_read_only_reconciliation(env):
    op=prepare(env);FakeService.fail=True
    assert c.exchange(env.db,env.actor,op.id).state=='unknown'
    with pytest.raises(t.ConnectionError,match='reconciliation_required'):c.exchange(env.db,env.actor,op.id)
    env.db.rollback();FakeService.fail=False
    assert c.exchange(env.db,env.actor,op.id,poll=True).state=='completed'
    assert FakeService.calls[-1][0]=='GET' and FakeService.calls[-1][2] is None
    assert len([x for x in FakeService.calls if '/operations/' in x[1] and x[0]=='POST'])==1


@pytest.mark.parametrize('tamper', [{'tenant_id':str(uuid.uuid4())},{'installation_id':str(uuid.uuid4())},{'operation_id':str(uuid.uuid4())},{'fingerprint':'wrong'},{'contract_version':'2'},{'state':'unknown'},{'credentials':{'password':'leak'}},{'result':{'access_token':'leak'}}])
def test_rejects_wrong_binding_contract_or_secret_result(env,tamper):
    op=prepare(env);FakeService.tamper=tamper
    result=c.exchange(env.db,env.actor,op.id)
    assert result.state=='unknown' and result.error_code=='invalid_response' and result.result_enc is None


def test_application_is_atomic_idempotent_and_works_offline(env,monkeypatch):
    op=prepare(env);c.exchange(env.db,env.actor,op.id)
    c.disconnect(env.db,env.actor,1)
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ENABLED','0')
    assert c.apply_result(env.db,env.actor,op.id).state=='applied'
    c.apply_result(env.db,env.actor,op.id)
    assert env.db.scalar(select(func.count()).select_from(env.effects))==1
    assert env.db.scalar(select(func.count()).select_from(CommercialApplication))==1


def test_failed_application_rolls_back_and_can_retry(env,monkeypatch):
    op=prepare(env);c.exchange(env.db,env.actor,op.id)
    good=c.ADAPTERS['synthetic.v1']
    def broken(db,op,result):
        db.execute(env.effects.insert().values(id=1))
        raise ValueError('synthetic failure')
    c.ADAPTERS['synthetic.v1']=c.Adapter(good.credential_key,good.validate_request,good.validate_result,broken)
    with pytest.raises(ValueError):c.apply_result(env.db,env.actor,op.id)
    assert env.db.scalar(select(func.count()).select_from(env.effects))==0
    assert env.db.get(CommercialApplication,op.id) is None
    c.ADAPTERS['synthetic.v1']=good
    c.apply_result(env.db,env.actor,op.id)
    assert env.db.scalar(select(func.count()).select_from(env.effects))==1


def test_changed_origin_cannot_receive_credentials(env,monkeypatch):
    op=prepare(env);n=len(FakeService.calls)
    monkeypatch.setenv('CANARY_COMMERCIAL_SERVICE_ORIGIN','https://different.example.test')
    with pytest.raises(t.ConnectionError,match='not_connected'):c.exchange(env.db,env.actor,op.id)
    assert len(FakeService.calls)==n


def test_no_registered_provider_and_secret_payload_rejected(env):
    with pytest.raises(t.ConnectionError,match='unsupported_adapter'):
        c.prepare(env.db,env.actor,env.case,'unregistered',uuid.uuid4(),{})
    with pytest.raises(t.ConnectionError,match='credentials_in_payload'):c.reject_credentials({'nested':[{'refresh_token':'secret'}]})


def test_service_status_and_vault_routes_require_admin(env):
    from app.routers import commercial_connection as router
    from app.deps import require_admin
    from app.db import get_db
    app=FastAPI();app.include_router(router.router)
    app.dependency_overrides[get_db]=lambda: env.db
    def deny():raise HTTPException(403)
    app.dependency_overrides[require_admin]=deny
    with TestClient(app) as client:
        for method,path in [('GET','status'),('POST','activate'),('POST','disconnect'),('GET','credentials/synthetic'),('PUT','credentials/synthetic')]:
            assert client.request(method,'/commercial-connection/'+path,json={'expected_version':0,'activation_code':'secret'}).status_code==403


def test_transport_redacts_errors_and_refuses_redirect(monkeypatch):
    import httpx
    real=httpx.AsyncClient
    seen=[]
    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(302,headers={'Location':'https://evil.test'},json={'password':'must-not-escape'})
    monkeypatch.setattr(t.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    with pytest.raises(t.ConnectionError,match='remote_rejected') as err:
        t.Transport('https://commercial.example.test').request('POST','/v1/operations/x',{'credentials':{'password':'synthetic'}})
    assert 'must-not-escape' not in str(err.value) and len(seen)==1


def test_validation_errors_never_echo_secret_input(env):
    from app.routers import commercial_connection as router
    from app.deps import require_admin
    from app.db import get_db
    app=FastAPI();app.include_router(router.router)
    app.dependency_overrides[get_db]=lambda: env.db
    app.dependency_overrides[require_admin]=lambda:env.actor
    with TestClient(app) as client:
        for body in [{'activation_code':{'password':'do-not-echo'},'expected_version':1},
                     {'activation_code':'do-not-echo','extra':'do-not-echo','expected_version':1}]:
            response=client.post('/commercial-connection/activate',json=body)
            assert response.status_code==422 and 'do-not-echo' not in response.text


def test_adapter_cannot_commit_before_receipt(env):
    op=prepare(env);c.exchange(env.db,env.actor,op.id)
    good=c.ADAPTERS['synthetic.v1']
    def broken(db,op,result):
        db.execute(env.effects.insert().values(id=1));db.commit()
    c.ADAPTERS['synthetic.v1']=c.Adapter(good.credential_key,good.validate_request,good.validate_result,broken)
    with pytest.raises(t.ConnectionError,match='adapter_commit_forbidden'):c.apply_result(env.db,env.actor,op.id)
    assert env.db.scalar(select(func.count()).select_from(env.effects))==0


def test_concurrent_disconnect_response_cannot_reconnect_or_apply(env,monkeypatch):
    op=prepare(env)
    original=FakeService.request
    def disconnecting(self,method,path,body=None,secret=None):
        response=original(self,method,path,body,secret)
        with Session(env.engine) as other:c.disconnect(other,env.actor,1)
        return response
    monkeypatch.setattr(FakeService,'request',disconnecting)
    with pytest.raises(t.ConnectionError,match='connection_changed'):c.exchange(env.db,env.actor,op.id)
    env.db.rollback()
    assert not c.status(env.db)['connected']
    assert env.db.get(CommercialOperation,op.id).state=='unknown'


def test_serialized_contract_through_real_http_transport(env,monkeypatch):
    import httpx
    real=httpx.AsyncClient
    fake=FakeService('https://commercial.example.test')
    captured=[]
    def respond(request):
        assert request.headers['X-Canary-Contract']=='1'
        assert request.headers['Authorization'].startswith('Bearer ')
        body=json.loads(request.content) if request.content else None
        captured.append(body)
        return httpx.Response(200,json=fake.request(request.method,request.url.path,body))
    monkeypatch.setattr(t.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    monkeypatch.setattr(c,'Transport',t.Transport)
    op=prepare(env)
    assert c.exchange(env.db,env.actor,op.id).state=='completed'
    c.apply_result(env.db,env.actor,op.id)
    assert captured[0]['credentials']=={'password':'synthetic-password'}
    assert env.db.scalar(select(func.count()).select_from(env.effects))==1


def test_pending_and_definitive_failure_do_not_resubmit(env):
    op=prepare(env);FakeService.tamper={'state':'pending'}
    assert c.exchange(env.db,env.actor,op.id).state=='submitted'
    FakeService.tamper={'state':'failed'}
    assert c.exchange(env.db,env.actor,op.id,poll=True).state=='failed'
    assert c.exchange(env.db,env.actor,op.id).state=='failed'
    assert len([x for x in FakeService.calls if '/operations/' in x[1] and x[0]=='POST'])==1


def test_adapter_rollback_cannot_be_recorded_as_applied(env):
    op=prepare(env);identity=op.id;c.exchange(env.db,env.actor,identity)
    good=c.ADAPTERS['synthetic.v1']
    def broken(db,op,result):db.rollback()
    c.ADAPTERS['synthetic.v1']=c.Adapter(good.credential_key,good.validate_request,good.validate_result,broken)
    with pytest.raises(t.ConnectionError,match='adapter_transaction_changed'):c.apply_result(env.db,env.actor,identity)
    assert env.db.get(CommercialOperation,identity).state=='completed'
    assert env.db.get(CommercialApplication,identity) is None


def test_transport_size_limit(env,monkeypatch):
    import httpx
    real=httpx.AsyncClient
    monkeypatch.setattr(t.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*(t.MAX_BYTES+1))),**kw))
    with pytest.raises(t.ConnectionError,match='invalid_response'):t.Transport('https://commercial.example.test').request('GET','/v1/operations/synthetic')

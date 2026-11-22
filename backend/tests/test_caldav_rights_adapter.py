"""Fail-closed behavior of the deployed Radicale adapter (no network calls)."""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import runpy
import sys
import types
import pytest

@pytest.fixture
def adapter(monkeypatch,tmp_path):
    class BaseRights:
        def __init__(self,configuration):self.configuration=configuration
    radicale=types.ModuleType('radicale');rights=types.ModuleType('radicale.rights');rights.BaseRights=BaseRights
    monkeypatch.setitem(sys.modules,'radicale',radicale);monkeypatch.setitem(sys.modules,'radicale.rights',rights)
    ns=runpy.run_path(str(Path(__file__).resolve().parents[2]/'radicale/config/canary_rights.py'))
    key=tmp_path/'users';key.write_bytes(b'synthetic-private-hash-file')
    class Config:
        def get(self,section,option):return str(key)
    return ns,ns['Rights'](Config()),key


def test_adapter_requires_request_context_and_authenticated_user(adapter,monkeypatch):
    ns,rights,_=adapter
    def never(*a,**k):raise AssertionError('Must not call Core')
    monkeypatch.setitem(rights.authorization.__globals__,'urlopen',never)
    assert rights.authorization('user','/user/')==''
    token=ns['request_context'].set(('GET','/user/calendar/item.ics'))
    try:assert rights.authorization('','/user/')==''
    finally:ns['request_context'].reset(token)

@pytest.mark.parametrize('response',[b'not-json',b'{"rights":"admin"}',b'{"rights":null}',None])
def test_adapter_denies_outages_and_invalid_responses(adapter,monkeypatch,response):
    ns,rights,_=adapter
    @contextmanager
    def endpoint(*a,**k):
        if response is None:raise TimeoutError()
        yield types.SimpleNamespace(read=lambda n:response)
    monkeypatch.setitem(rights.authorization.__globals__,'urlopen',endpoint)
    token=ns['request_context'].set(('GET','/owner/calendar/item.ics'))
    try:assert rights.authorization('reader','/owner/calendar/')==''
    finally:ns['request_context'].reset(token)


def test_adapter_signs_context_and_does_not_cache_permissions(adapter,monkeypatch):
    ns,rights,key=adapter;calls=[]
    @contextmanager
    def endpoint(request,timeout):
        payload=json.loads(request.data);calls.append(payload)
        expected=hmac.new(hashlib.sha256(b'canary-caldav-rights-v1\0'+key.read_bytes()).digest(),request.data,hashlib.sha256).hexdigest()
        assert request.get_header('X-canary-dav-signature')==expected
        assert payload['method']=='DELETE' and payload['request_path']=='/owner/team/item.ics'
        yield types.SimpleNamespace(read=lambda n:b'{"rights":"rw"}' if len(calls)==1 else b'{"rights":""}')
    monkeypatch.setitem(rights.authorization.__globals__,'urlopen',endpoint)
    token=ns['request_context'].set(('DELETE','/owner/team/item.ics'))
    try:
        assert rights.authorization('editor','/owner/team/')=='rw'
        assert rights.authorization('editor','/owner/team/')==''
    finally:ns['request_context'].reset(token)

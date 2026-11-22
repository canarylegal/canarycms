"""Service-level worker isolation; real PostgreSQL lock waits are exercised by E2E."""
import asyncio
import threading
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from app.document_io import document_io


@pytest.mark.asyncio
async def test_contended_document_request_does_not_block_other_requests():
    app = FastAPI()
    entered = threading.Event()
    release = threading.Event()
    @app.get('/save')
    @document_io
    async def save(version: int):
        entered.set()
        assert release.wait(3)
        raise HTTPException(409, f'stale {version}')
    @app.get('/health')
    async def health():
        return {'ok':True}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        pending = asyncio.create_task(client.get('/save?version=2'))
        try:
            async with asyncio.timeout(1):
                while not entered.is_set(): await asyncio.sleep(.01)
                response = await client.get('/health')
            assert response.status_code == 200
            assert not pending.done()
        finally:
            release.set()
        response = await pending
        assert response.status_code == 409 and response.json()['detail'] == 'stale 2'


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint_name,service_name,arguments',[
    ('oo_force_save_letterhead','_firm_letterhead_oo_force_save',{'doc_key':'test'}),
    ('oo_force_save_quote_letterhead','_firm_letterhead_oo_force_save',{'doc_key':'test'}),
    ('oo_persist_download_letterhead','_firm_letterhead_oo_persist_download',{'body':None}),
    ('oo_persist_download_quote_letterhead','_firm_letterhead_oo_persist_download',{'body':None}),
])
async def test_letterhead_save_services_also_leave_loop_responsive(monkeypatch,endpoint_name,service_name,arguments):
    from app.routers import admin_firm_settings
    entered=threading.Event();release=threading.Event()
    async def blocked_service(*args,**kwargs):
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(admin_firm_settings,service_name,blocked_service)
    pending=asyncio.create_task(getattr(admin_firm_settings,endpoint_name)(admin=None,db=None,**arguments))
    try:
        async with asyncio.timeout(1):
            while not entered.is_set():await asyncio.sleep(.01)
        assert not pending.done()
    finally:
        release.set()
    await pending

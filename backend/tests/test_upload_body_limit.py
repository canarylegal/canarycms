import anyio
import pytest
from app.upload_body_limit import UploadBodyLimitMiddleware

@pytest.mark.parametrize('path',['/cases/synthetic/files','/portal/grants/synthetic/files','/portal/forms/synthetic/upload','/precedents','/precedents/'])
@pytest.mark.parametrize('declared',[None,b'1',b'25'])
def test_oversize_never_reaches_app_even_without_accurate_content_length(monkeypatch,path,declared):
    from app import upload_body_limit as limits
    monkeypatch.setattr(limits,'max_upload_bytes',lambda:8);monkeypatch.setattr(limits,'MULTIPART_ALLOWANCE',16)
    events=[];called=[]
    async def app(scope,receive,send):called.append(True)
    async def run():
        chunks=iter([{'type':'http.request','body':b'x'*12,'more_body':True},{'type':'http.request','body':b'x'*13,'more_body':False}])
        async def receive():return next(chunks)
        async def send(message):events.append(message)
        await UploadBodyLimitMiddleware(app)({'type':'http','method':'POST','path':path,'headers':[(b'content-length',declared)] if declared else []},receive,send)
    anyio.run(run)
    assert not called
    assert events[0]['status']==413

@pytest.mark.parametrize('size',[0,24])
def test_allowed_body_is_replayed_unchanged(monkeypatch,size):
    from app import upload_body_limit as limits
    monkeypatch.setattr(limits,'max_upload_bytes',lambda:8);monkeypatch.setattr(limits,'MULTIPART_ALLOWANCE',16)
    got=bytearray()
    async def app(scope,receive,send):
        while True:
            event=await receive();got.extend(event['body'])
            if not event.get('more_body'):break
    async def receive():return {'type':'http.request','body':b'x'*size,'more_body':False}
    async def send(message):pass
    anyio.run(UploadBodyLimitMiddleware(app),{'type':'http','method':'POST','path':'/precedents','headers':[]},receive,send)
    assert got==b'x'*size

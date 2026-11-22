"""Authenticated Radicale-to-Core authorization callback; never accepts staff JWTs."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import hmac
import json
import time
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import DATABASE_URL, SessionLocal
from app.radicale_htpasswd import htpasswd_path
from app.caldav_permissions import calendar_rights

router = APIRouter()


# GUI handlers can wait on Radicale while holding ordinary DB connections and
# worker slots. The callback needs its own small pool to avoid a dependency cycle.
_workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix='caldav-rights')


@lru_cache(maxsize=1)
def rights_sessions():
    if DATABASE_URL.startswith('sqlite'):
        return SessionLocal
    engine = create_engine(DATABASE_URL, pool_size=4, max_overflow=0,
                           pool_timeout=2, pool_pre_ping=True,
                           connect_args={'connect_timeout': 2, 'options': '-cstatement_timeout=2000'})
    return sessionmaker(bind=engine)


def authorize(body, signature):
    # Both containers already hold this private credential file. Domain-separated
    # HMAC avoids a new deployment secret and never sends password hashes over HTTP.
    try:
        key_material = htpasswd_path().read_bytes()
    except OSError:
        key_material = b''
    expected = hmac.new(hashlib.sha256(b'canary-caldav-rights-v1\0' + key_material).digest(), body, hashlib.sha256).hexdigest()
    if not key_material.strip() or len(signature) != 64 or any(c not in '0123456789abcdef' for c in signature) or not hmac.compare_digest(expected, signature):
        raise HTTPException(403, 'Forbidden')
    try:
        payload = json.loads(body)
        if abs(time.time() - payload['timestamp']) > 30:
            raise ValueError()
        args = [payload[k] for k in ('user', 'path', 'method', 'request_path')]
        if not all(isinstance(v, str) for v in args):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(403, 'Forbidden') from None
    with rights_sessions()() as db:
        return calendar_rights(db, *args)


@router.post('/internal/caldav/rights', include_in_schema=False)
async def rights(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(413, 'Request too large')
    result = await asyncio.get_running_loop().run_in_executor(
        _workers, authorize, bytes(body), request.headers.get('X-Canary-DAV-Signature', ''))
    return JSONResponse({'rights': result}, headers={'Cache-Control': 'private, no-store'})

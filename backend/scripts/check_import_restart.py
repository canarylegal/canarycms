"""Upload/replay from independent processes on either side of an isolated restart."""
import hashlib
import io
import json
import os
import uuid
from pathlib import Path
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import User, Case, File, AuditEvent
from app.file_upload_service import upload_case_file
from fastapi import UploadFile

if os.getenv('CANARY_TEST_FIXTURE') != '1' or os.getenv('POSTGRES_DB') != 'canary_core_test':
    raise SystemExit('Requires the disposable core fixture')
body=b'Persistent import receipt after a backend restart\n'
key=uuid.UUID('5cad7803-b121-4218-9dd7-47713e77a517')
with SessionLocal() as db:
    user=db.scalar(select(User).where(User.email=='core.staff@example.com'))
    matter=db.scalar(select(Case).where(Case.case_number=='900001'))
    assert user is not None and matter is not None
    result=upload_case_file(matter.id,UploadFile(io.BytesIO(body),filename='restart-receipt.txt'),idempotency_key=key,user=user,db=db)
    row=db.get(File,uuid.UUID(result['id']))
    assert (Path(os.environ['FILES_ROOT'])/row.storage_path).read_bytes()==body
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action=='case.file.upload',AuditEvent.entity_id==result['id']))==1
    print(json.dumps({'id':result['id'],'sha256':hashlib.sha256(body).hexdigest(),'audit_events':1}))

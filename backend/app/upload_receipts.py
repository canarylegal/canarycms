"""Durable, caller-scoped receipts for explicit retries of matter uploads."""
import hashlib
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import text
from app.models.upload_receipts import UploadReceipt
from app.models.files_tasks import File
from app.upload_limits import max_upload_bytes



def receipt_id(case_id, user_id, key):
    return uuid.uuid5(uuid.NAMESPACE_URL, f'canary:upload:{case_id}:{user_id}:{key}')


def lock_receipt(db, operation_id):
    if db.bind.dialect.name == 'postgresql':
        lock_id = int.from_bytes(operation_id.bytes[:8], 'big', signed=True)
        if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': lock_id}):
            raise HTTPException(429, 'This upload is still processing. Wait a moment, then retry.')


def fingerprint_upload(upload, metadata):
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, default=str).encode())
    size = 0
    try:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > max_upload_bytes():
                raise HTTPException(413, 'This file is too large to upload.')
            digest.update(chunk)
    finally:
        upload.file.seek(0)
    return digest.hexdigest()


def replay_receipt(db, operation_id, fingerprint):
    receipt = db.get(UploadReceipt, operation_id)
    if receipt is None:
        return None
    if receipt.fingerprint != fingerprint:
        raise HTTPException(409, 'This upload retry contains different content or options. Start a new import.')
    if db.get(File, uuid.UUID(receipt.response['id'])) is None:
        raise HTTPException(410, 'The previously uploaded document was deleted. It will not be recreated by retrying.')
    return dict(receipt.response)

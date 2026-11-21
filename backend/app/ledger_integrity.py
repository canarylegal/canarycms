"""Transaction-scoped serialization, retry receipts and receipt eligibility."""
import hashlib
import json
import uuid
import zlib

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.models import InterMatterJournal, LedgerOperation


def lock_operation(db: Session, namespace: int, identity: str) -> None:
    if db.get_bind().dialect.name == 'postgresql':
        locked = db.scalar(text('SELECT pg_try_advisory_xact_lock(:namespace, :key)'),
            {'namespace': namespace, 'key': zlib.crc32(identity.encode()) & 0x7fffffff})
        if not locked:
            raise HTTPException(409, 'This financial operation is in progress. Retry with the same request ID.')


def lock_matters(db: Session, *case_ids: uuid.UUID) -> None:
    # Acquire both ends before touching accounts; opposite transfers cannot deadlock.
    for case_id in sorted(set(case_ids)):
        lock_operation(db, 582013720, str(case_id))


def request_receipt(db, actor, kind, payload, context):
    key = payload.idempotency_key
    fingerprint = hashlib.sha256(json.dumps(
        {'kind': kind, 'context': str(context), 'payload': payload.model_dump(mode='json', exclude={'idempotency_key'})},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if key is not None:
        lock_operation(db, 582013721, f'{actor.id}:{key}')
        previous = db.scalar(select(LedgerOperation).where(
            LedgerOperation.actor_user_id == actor.id, LedgerOperation.request_key == key))
        if previous:
            if previous.fingerprint != fingerprint or previous.kind != kind:
                raise HTTPException(409, 'This request ID was already used for different details')
            return fingerprint, previous
    return fingerprint, None


def record_receipt(db, actor, kind, payload, fingerprint, result_id, result, *, reverses_id=None):
    db.add(LedgerOperation(actor_user_id=actor.id, request_key=payload.idempotency_key,
        kind=kind, fingerprint=fingerprint, result_id=result_id, result_json=json.dumps(result, default=str),
        reverses_id=reverses_id))
    db.flush()


def require_external_receipt(db: Session, pair_id: uuid.UUID) -> None:
    journal = db.scalar(select(InterMatterJournal.id).where(or_(
        InterMatterJournal.from_pair_id == pair_id, InterMatterJournal.to_pair_id == pair_id)).limit(1))
    reversal = db.scalar(select(LedgerOperation.id).where(
        LedgerOperation.kind == 'reverse_posting', or_(LedgerOperation.reverses_id == pair_id,
                                                       LedgerOperation.result_id == pair_id)).limit(1))
    if journal or reversal:
        raise HTTPException(409, 'Transfers and reversed or compensating postings cannot be used as receipts or bank matches')

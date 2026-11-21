"""Replay one office posting from separate processes across an isolated backend restart."""
import json
import os
import uuid
from sqlalchemy import func, select
from app.db import SessionLocal
from app.ledger_operations import post_ledger_operation
from app.models import AuditEvent, Case, LedgerEntry, User
from app.schemas import LedgerPostCreate

if os.getenv('CANARY_TEST_FIXTURE') != '1' or os.getenv('POSTGRES_DB') != 'canary_core_test':
    raise SystemExit('Requires the disposable core fixture')
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == 'core.approver@example.com'))
    matter = db.scalar(select(Case).where(Case.case_number == '900001'))
    assert user is not None and matter is not None
    result = post_ledger_operation(matter.id, LedgerPostCreate(description='Restart-safe office receipt',
        amount_pence=100, office_direction='credit', idempotency_key=uuid.UUID('9780d1f1-5f3e-4d3f-b2b5-03324c067834')), user, db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.pair_id == result.pair_id)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.entity_id == str(result.pair_id), AuditEvent.action == 'ledger.post')) == 1
    print(json.dumps({'pair_id': str(result.pair_id), 'entries': 1, 'audits': 1}))

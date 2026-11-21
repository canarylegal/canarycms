"""Shared bank-operation locks, authorisation and closed-period guards."""
import uuid
import zlib
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import BankReconciliation, User
from app.permission_checks import user_may_access_accounts_workspace


def require_banking(actor: User, db: Session) -> None:
    if not actor.is_active or not user_may_access_accounts_workspace(actor, db):
        raise HTTPException(403, 'Accounts workspace required')


def lock_bank(db: Session, bank_id: uuid.UUID) -> None:
    if db.get_bind().dialect.name == 'postgresql':
        locked = db.scalar(text('SELECT pg_try_advisory_xact_lock(:namespace, :key)'),
            {'namespace': 582013719, 'key': zlib.crc32(bank_id.bytes) & 0x7fffffff})
        if not locked:
            raise HTTPException(409, 'This bank is being updated. Refresh and try again.')


def require_open_period(db: Session, bank_id: uuid.UUID, statement_date: date) -> None:
    closed = db.scalar(select(BankReconciliation.id).where(
        BankReconciliation.firm_bank_account_id == bank_id,
        BankReconciliation.status == 'approved',
        BankReconciliation.period_end_date >= statement_date).limit(1))
    if closed:
        raise HTTPException(409, 'This statement period is approved. Reopen the reconciliation with a reason before correcting it.')

"""Versioned, audited bank matching; all mutations commit in the caller's transaction."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.bank_integrity import lock_bank, require_banking, require_open_period
from app.deps import require_case_access
from app.ledger_service import _try_lock_ledger_pair
from app.models import AuditEvent, BankStatementLine, LedgerAccount, LedgerAccountType, LedgerDirection, LedgerEntry, User


def _locked_line(db: Session, line_id: uuid.UUID, actor: User) -> BankStatementLine:
    require_banking(actor, db)
    line = db.get(BankStatementLine, line_id)
    if line is None:
        raise HTTPException(404, 'Statement line not found')
    lock_bank(db, line.firm_bank_account_id)
    return db.scalars(select(BankStatementLine).where(BankStatementLine.id == line_id)
        .with_for_update().execution_options(populate_existing=True)).one()


def _state(line: BankStatementLine) -> dict:
    return {'matched_pair_id': str(line.matched_pair_id) if line.matched_pair_id else None,
            'ignored': line.ignored, 'version': line.version,
            'matched_at': line.matched_at.isoformat() if line.matched_at else None,
            'matched_by_user_id': str(line.matched_by_user_id) if line.matched_by_user_id else None}


def _version(line: BankStatementLine, expected_version: int) -> None:
    if line.version != expected_version:
        raise HTTPException(409, 'This statement line changed. Refresh before making another correction.')


def _authorise_pair(db: Session, pair_id: uuid.UUID, actor: User) -> None:
    case_ids = db.scalars(select(LedgerAccount.case_id).join(LedgerEntry,
        LedgerEntry.account_id == LedgerAccount.id).where(LedgerEntry.pair_id == pair_id).distinct())
    for case_id in case_ids:
        require_case_access(case_id, actor, db)


def _eligible_pair(db: Session, line: BankStatementLine, pair_id: uuid.UUID, actor: User) -> None:
    _try_lock_ledger_pair(db, pair_id)
    _authorise_pair(db, pair_id, actor)
    from app.ledger_integrity import require_external_receipt
    require_external_receipt(db, pair_id)
    legs = list(db.scalars(select(LedgerEntry).join(LedgerAccount).where(
        LedgerEntry.pair_id == pair_id, LedgerAccount.account_type == LedgerAccountType.client)))
    if len(legs) != 1:
        raise HTTPException(400, 'Match requires exactly one client bank posting')
    leg = legs[0]
    signed = leg.amount_pence if leg.direction == LedgerDirection.credit else -leg.amount_pence
    if (not leg.is_approved or leg.is_anticipated or leg.amount_pence <= 0
            or leg.firm_bank_account_id != line.firm_bank_account_id or signed != line.amount_pence):
        raise HTTPException(400, 'Match requires an approved posting on the same bank with the same signed amount')
    duplicate = db.scalar(select(BankStatementLine.id).where(
        BankStatementLine.matched_pair_id == pair_id, BankStatementLine.id != line.id).limit(1))
    if duplicate:
        raise HTTPException(409, 'This posting is already matched to another statement line')


def _change(db: Session, line: BankStatementLine, actor: User, *, pair_id: uuid.UUID | None,
            ignored: bool, action: str, reason: str | None = None) -> BankStatementLine:
    before = _state(line)
    if line.matched_pair_id == pair_id and line.ignored == ignored:
        return line
    require_open_period(db, line.firm_bank_account_id, line.statement_date)
    if line.matched_pair_id:
        _authorise_pair(db, line.matched_pair_id, actor)
    if pair_id:
        _eligible_pair(db, line, pair_id, actor)
    line.matched_pair_id = pair_id
    line.ignored = ignored
    line.matched_at = datetime.now(timezone.utc) if pair_id else None
    line.matched_by_user_id = actor.id if pair_id else None
    line.version += 1
    db.flush()
    log_event(db, actor_user_id=actor.id, action=f'bank.statement.{action}',
        entity_type='bank_statement_line', entity_id=str(line.id),
        meta={'bank_id': str(line.firm_bank_account_id), 'before': before, 'after': _state(line), 'reason': reason})
    return line


def match_line(db: Session, *, line_id: uuid.UUID, ledger_pair_id: uuid.UUID,
               actor: User, expected_version: int) -> BankStatementLine:
    line = _locked_line(db, line_id, actor)
    _version(line, expected_version)
    if line.matched_pair_id and line.matched_pair_id != ledger_pair_id:
        raise HTTPException(409, 'Unmatch the current posting before choosing a different one')
    if line.ignored:
        raise HTTPException(409, 'Restore the ignored statement line before matching it')
    _eligible_pair(db, line, ledger_pair_id, actor)
    return _change(db, line, actor, pair_id=ledger_pair_id, ignored=False, action='match')


def unmatch_line(db: Session, *, line_id: uuid.UUID, actor: User, expected_version: int) -> BankStatementLine:
    line = _locked_line(db, line_id, actor)
    _version(line, expected_version)
    return _change(db, line, actor, pair_id=None, ignored=line.ignored, action='unmatch')


def ignore_line(db: Session, *, line_id: uuid.UUID, actor: User, expected_version: int,
                ignored: bool = True) -> BankStatementLine:
    line = _locked_line(db, line_id, actor)
    _version(line, expected_version)
    return _change(db, line, actor, pair_id=None if ignored else line.matched_pair_id,
                   ignored=ignored, action='ignore' if ignored else 'unignore')


def line_history(db: Session, *, line_id: uuid.UUID, actor: User) -> list[AuditEvent]:
    line = _locked_line(db, line_id, actor)
    if line.matched_pair_id:
        _authorise_pair(db, line.matched_pair_id, actor)
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.entity_type == 'bank_statement_line',
        AuditEvent.entity_id == str(line_id)).order_by(AuditEvent.created_at, AuditEvent.id)))
    for event in events:
        changes = json.loads(event.meta_json)
        for state in ('before', 'after'):
            pair = changes.get(state, {}).get('matched_pair_id')
            if pair:
                _authorise_pair(db, uuid.UUID(pair), actor)
    return events


def restore_line(db: Session, *, line_id: uuid.UUID, event_id: uuid.UUID, expected_version: int,
                 actor: User, reason: str) -> BankStatementLine:
    line = _locked_line(db, line_id, actor)
    _version(line, expected_version)
    if not reason.strip():
        raise HTTPException(400, 'A correction reason is required')
    event = db.get(AuditEvent, event_id)
    if (event is None or event.entity_type != 'bank_statement_line' or event.entity_id != str(line_id)
            or event.action not in {'bank.statement.match', 'bank.statement.unmatch', 'bank.statement.ignore',
                                    'bank.statement.unignore', 'bank.statement.restore'}):
        raise HTTPException(404, 'Statement correction event not found')
    before = json.loads(event.meta_json)['before']
    pair_id = uuid.UUID(before['matched_pair_id']) if before['matched_pair_id'] else None
    return _change(db, line, actor, pair_id=pair_id, ignored=before['ignored'], action='restore',
                   reason=f'{reason.strip()} (undo {event_id})')

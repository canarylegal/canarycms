"""Operator-only historical review and explicit, preview-bound corrections.

No caller should commit a correction until the exact plan has been reviewed.
Database/host access is the CLI security boundary, not possession of a plan hash.
"""
import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.audit import log_event
from app.bank_integrity import lock_bank, require_open_period
from app.bank_matching_service import _state, unmatch_line
from app.ledger_service import _try_lock_ledger_pair
from app.models import (AuditEvent, BankReconciliation, BankStatementLine, CaseInvoice,
                        LedgerEntry, User, UserRole)
from app.financial_validation import validate_financial_data

ACTION = 'financial.correction.unmatch_missing_posting'


def _time(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def preview_unmatch(db, line_id):
    """SELECT-only proposal, including conditions that block execution."""
    line = db.get(BankStatementLine, line_id)
    if line is None:
        raise HTTPException(404, 'Statement line not found')
    legs = list(db.scalars(select(LedgerEntry.id).where(LedgerEntry.pair_id == line.matched_pair_id))) if line.matched_pair_id else []
    closed = list(db.scalars(select(BankReconciliation.id).where(
        BankReconciliation.firm_bank_account_id == line.firm_bank_account_id,
        BankReconciliation.status == 'approved',
        BankReconciliation.period_end_date >= line.statement_date).order_by(BankReconciliation.id)))
    blockers = []
    if not line.matched_pair_id:
        blockers.append('line_is_not_matched')
    if legs:
        blockers.append('posting_exists_requires_separate_review')
    if closed:
        blockers.append('approved_period_requires_reasoned_reopen')
    before = dict(_state(line), matched_at=_time(line.matched_at),
                  bank_id=str(line.firm_bank_account_id), import_id=str(line.import_id),
                  statement_date=line.statement_date.isoformat(), amount_pence=line.amount_pence,
                  balance_pence=line.balance_pence,
                  source_hash=_digest([line.description, line.reference]))
    plan = dict(schema_version=1, operation='unmatch_missing_posting', line_id=str(line.id),
                before=before, after=dict(matched_pair_id=None, matched_at=None,
                matched_by_user_id=None, ignored=line.ignored, version=line.version+1),
                posting_leg_ids=sorted(map(str, legs)), closed_reconciliation_ids=list(map(str, closed)),
                blockers=blockers, ledger_effect='none',
                report_effect='Statement becomes unmatched; review reconciliation before approving it.')
    return dict(plan, plan_hash=_digest(plan))


def apply_unmatch(db, *, plan, actor_id, reason, approved_hash):
    """Atomic mutation + receipt; caller commits once. No timestamp repair supported."""
    actor = db.get(User, actor_id)
    if actor is None or not actor.is_active or actor.role != UserRole.admin:
        raise HTTPException(403, 'An active administrator is required')
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1000:
        raise HTTPException(400, 'A review reason of 10 to 1000 characters is required')
    payload = {k:v for k,v in plan.items() if k != 'plan_hash'}
    if approved_hash != plan.get('plan_hash') or approved_hash != _digest(payload):
        raise HTTPException(409, 'Approval does not match the complete preview')
    line_id = uuid.UUID(plan['line_id'])
    line = db.get(BankStatementLine, line_id)
    if line is None:
        raise HTTPException(404, 'Statement line not found')
    lock_bank(db, line.firm_bank_account_id)
    db.refresh(line, with_for_update=True)
    # Bank lock serializes receipts with all statement operations. A receipt means
    # this exact operation committed, even if a later operation changed the line.
    receipt = db.scalar(select(AuditEvent).where(AuditEvent.action == ACTION,
        AuditEvent.entity_id == approved_hash, AuditEvent.entity_type == 'financial_correction'))
    if receipt:
        return dict(status='already_applied', plan_hash=approved_hash, audit_id=str(receipt.id))
    if line.matched_pair_id:
        _try_lock_ledger_pair(db, line.matched_pair_id)
    current = preview_unmatch(db, line_id)
    if current != plan:
        raise HTTPException(409, 'Evidence changed; generate and review a new preview')
    if current['blockers']:
        raise HTTPException(409, 'Preview has unresolved blockers')
    require_open_period(db, line.firm_bank_account_id, line.statement_date)
    unmatch_line(db, line_id=line_id, actor=actor, expected_version=line.version)
    log_event(db, actor_user_id=actor.id, action=ACTION, entity_type='financial_correction',
              entity_id=approved_hash, meta=dict(plan_hash=approved_hash, line_id=str(line.id),
              before=plan['before'], after=_state(line), reason=reason.strip()))
    receipt = db.scalar(select(AuditEvent).where(AuditEvent.action == ACTION,
        AuditEvent.entity_id == approved_hash, AuditEvent.entity_type == 'financial_correction'))
    return dict(status='applied', plan_hash=approved_hash, audit_id=str(receipt.id))


def investigate_history(db):
    """Private, reproducible evidence inventory; no inferred approvals or repairs."""
    validation = validate_financial_data(db)
    gaps = {f['id'] for f in validation['findings'] if f['code'] in
            ('missing_approval_evidence', 'approval_time_recovery_available')}
    events = defaultdict(list)
    all_events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at, AuditEvent.id)))
    for event in all_events:
        if event.entity_id in gaps:
            events[event.entity_id].append(dict(id=str(event.id), action=event.action, at=_time(event.created_at)))
    referenced_events = defaultdict(list)
    for event in all_events:
        references = set(re.findall(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', (event.meta_json or '').lower()))
        for pair in references & gaps:
            referenced_events[pair].append(dict(id=str(event.id), action=event.action, at=_time(event.created_at)))
    invoice_links = defaultdict(list)
    for invoice in db.scalars(select(CaseInvoice)):
        for pair, at, kind in [(invoice.ledger_pair_id, invoice.approved_at, 'approval'),
                               (invoice.reversal_pair_id, invoice.voided_at, 'void')]:
            if pair and str(pair) in gaps:
                invoice_links[str(pair)].append(dict(invoice_id=str(invoice.id), kind=kind, at=_time(at)))
    pairs = defaultdict(list)
    for leg in db.scalars(select(LedgerEntry).order_by(LedgerEntry.id)):
        if str(leg.pair_id) in gaps:
            pairs[str(leg.pair_id)].append(dict(id=str(leg.id), account_id=str(leg.account_id),
                amount_pence=leg.amount_pence, direction=leg.direction.value,
                posted_at=_time(leg.posted_at), recognised_at=_time(leg.recognised_at),
                approved=leg.is_approved, anticipated=leg.is_anticipated))
    evidence = [dict(pair_id=pair, ledger_fingerprint=_digest(legs), legs=legs,
                     audit_events=events[pair], metadata_reference_events=referenced_events[pair], invoice_links=invoice_links[pair],
                     disposition='review_evidence_only') for pair, legs in sorted(pairs.items())]
    matches = []
    for finding in validation['findings']:
        if finding['code'] == 'invalid_bank_match':
            plan = preview_unmatch(db, uuid.UUID(finding['id']))
            related = [dict(id=str(e.id), action=e.action, at=_time(e.created_at)) for e in all_events
                       if e.entity_id in (finding['id'], finding['evidence']['pair_id'])]
            matches.append(dict(finding=finding, preview=plan, audit_events=related))
    return dict(schema_version=1, summary=validation['summary'], bank_matches=matches,
                approval_evidence=evidence,
                posting_months=dict(sorted(Counter(leg['posted_at'][:7] for item in evidence for leg in item['legs']).items())),
                audit_coverage=dict(total_events=len(all_events), earliest=_time(all_events[0].created_at) if all_events else None,
                                    latest=_time(all_events[-1].created_at) if all_events else None),
                limitations=['Evidence absence is not proof of incorrect balances or approval dates.',
                             'Compare pair fingerprints and event IDs across independent backups.',
                             'No automatic replacement matches, ledger recreation or approval-date backfill.'])

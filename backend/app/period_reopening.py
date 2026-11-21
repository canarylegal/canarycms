"""Review-bound firm-wide reopening without new UI or historical data rewrites."""
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.accounting_periods import lock_periods, period_impact
from app.audit import log_event
from app.models import AuditEvent, ClientAccountReconciliation, ReconciliationStatus, User
from app.permission_checks import user_may_approve_ledger


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _snapshot(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
        elif value is not None and not isinstance(value, (str, int, bool)):
            value = str(value)
        result[column.name] = value
    return result


def preview_reopening(db, reconciliation_id):
    row = db.get(ClientAccountReconciliation, reconciliation_id)
    if row is None:
        raise HTTPException(404, 'Firm-wide reconciliation not found')
    snapshot = _snapshot(row)
    # Hash notes, rather than exporting client-sensitive prose in operator previews.
    snapshot['notes_hash'] = _hash(snapshot.pop('notes'))
    preview = dict(schema_version=1, operation='reopen_firm_period', before=snapshot,
                   review_scope=period_impact(db, row.period_end_date),
                   blockers=[] if row.status == ReconciliationStatus.approved else ['not_approved'])
    return dict(preview, preview_hash=_hash(preview))


def reopen_period(db, *, reconciliation_id, actor_id, expected_hash, reason):
    actor = db.get(User, actor_id)
    if actor is None or not actor.is_active or not user_may_approve_ledger(actor, db):
        raise HTTPException(403, 'Active reconciliation approver required')
    if not reason.strip() or len(reason.strip()) > 1000:
        raise HTTPException(400, 'A review reason of at most 1000 characters is required')
    lock_periods(db, exclusive=True)
    row = db.scalar(select(ClientAccountReconciliation).where(ClientAccountReconciliation.id == reconciliation_id)
                    .with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, 'Firm-wide reconciliation not found')
    for previous in db.scalars(select(AuditEvent).where(AuditEvent.action == 'reconciliation.reopen',
            AuditEvent.entity_id == str(row.id))):
        if json.loads(previous.meta_json or '{}').get('preview_hash') == expected_hash:
            return dict(status='already_reopened', audit_id=str(previous.id), preview_hash=expected_hash)
    preview = preview_reopening(db, row.id)
    if preview['preview_hash'] != expected_hash or preview['blockers']:
        raise HTTPException(409, 'Reconciliation or review scope changed; review a fresh preview')
    before = preview['before']
    row.status = ReconciliationStatus.draft
    row.approved_at = None
    row.approved_by_user_id = None
    db.flush()
    log_event(db, actor_user_id=actor.id, action='reconciliation.reopen',
              entity_type='client_account_reconciliation', entity_id=str(row.id),
              meta=dict(before=before, after=dict(status='draft', approved_at=None, approved_by_user_id=None),
                        reason=reason.strip(), preview_hash=expected_hash,
                        review_scope=period_impact(db, row.period_end_date)))
    return dict(status='reopened', preview_hash=expected_hash)

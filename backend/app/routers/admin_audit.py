import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Session

from app.audit_display import extract_case_id, format_audit_summary, parse_audit_meta
from app.db import get_db
from app.deps import require_admin
from app.models import AuditEvent, Case, CaseAccessRule, CaseContact, CaseNote, CaseTask, File, User


ACCOUNTS_AUDIT_ACTIONS = (
    "ledger.post",
    "ledger.approve",
    "invoice.create",
    "invoice.approve",
    "invoice.void",
    "reconciliation.create",
    "reconciliation.update",
    "reconciliation.approve",
)

router = APIRouter(prefix="/admin/audit-events", tags=["admin-audit"])

# Entity types that reference a matter by FK; used for legacy rows missing meta.case_id.
_MATTER_ENTITY_MODELS: dict[str, type] = {
    "file": File,
    "case_contact": CaseContact,
    "case_task": CaseTask,
    "case_note": CaseNote,
    "case_access_rule": CaseAccessRule,
}


class AdminAuditEventOut(BaseModel):
    id: str
    actor_user_id: str | None
    actor_display_name: str | None
    actor_initials: str | None
    action: str
    summary: str
    entity_type: str | None
    entity_id: str | None
    case_id: str | None
    case_number: str | None
    case_title: str | None
    ip: str | None
    user_agent: str | None
    meta: dict | None
    created_at: datetime


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _entity_id_matches(model: type, db: Session):
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return model.id == cast(AuditEvent.entity_id, PGUUID(as_uuid=True))
    return func.replace(cast(model.id, String), "-", "") == func.replace(AuditEvent.entity_id, "-", "")


def _matter_entity_filter(db: Session, case_id: uuid.UUID, entity_type: str, model: type):
    return and_(
        AuditEvent.entity_type == entity_type,
        AuditEvent.entity_id.isnot(None),
        exists(
            select(1).where(
                _entity_id_matches(model, db),
                model.case_id == case_id,
            )
        ),
    )


def _batch_resolve_case_ids(
    db: Session,
    events: list[AuditEvent],
    parsed_meta: list[dict | None],
) -> list[str | None]:
    """Resolve matter id from meta, case entity, or linked row (file, contact, task, etc.)."""
    resolved: list[str | None] = [None] * len(events)
    pending: dict[str, dict[str, list[int]]] = {key: defaultdict(list) for key in _MATTER_ENTITY_MODELS}

    for i, (event, meta) in enumerate(zip(events, parsed_meta)):
        cid = extract_case_id(entity_type=event.entity_type, entity_id=event.entity_id, meta=meta)
        if cid:
            resolved[i] = cid
            continue
        entity_type = event.entity_type
        entity_id = event.entity_id
        if entity_type in pending and entity_id:
            pending[entity_type][entity_id].append(i)

    for entity_type, model in _MATTER_ENTITY_MODELS.items():
        by_entity_id = pending[entity_type]
        if not by_entity_id:
            continue
        uuids: list[uuid.UUID] = []
        for raw in by_entity_id:
            try:
                uuids.append(uuid.UUID(raw))
            except ValueError:
                continue
        if not uuids:
            continue
        rows = db.execute(select(model.id, model.case_id).where(model.id.in_(uuids))).all()
        for row_id, case_id in rows:
            cid = str(case_id)
            for idx in by_entity_id.get(str(row_id), []):
                resolved[idx] = cid

    return resolved


def _case_id_filter(db: Session, case_id: uuid.UUID):
    """Match audit rows tied to a matter via meta, entity, or linked file/contact."""
    cid = str(case_id)
    parts: list = [and_(AuditEvent.entity_type == "case", AuditEvent.entity_id == cid)]

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        parts.append(cast(AuditEvent.meta_json, JSONB)["case_id"].astext == cid)
    else:
        parts.append(AuditEvent.meta_json.contains(f'"case_id":"{cid}"'))

    for entity_type, model in _MATTER_ENTITY_MODELS.items():
        parts.append(_matter_entity_filter(db, case_id, entity_type, model))
    return or_(*parts)


def _serialize_events(db: Session, events: list[AuditEvent]) -> list[AdminAuditEventOut]:
    actor_ids = {e.actor_user_id for e in events if e.actor_user_id}
    users: dict[uuid.UUID, User] = {}
    if actor_ids:
        rows = db.execute(select(User).where(User.id.in_(actor_ids))).scalars().all()
        users = {u.id: u for u in rows}

    case_ids: set[str] = set()
    parsed_meta: list[dict | None] = []
    for e in events:
        parsed_meta.append(parse_audit_meta(e.meta_json))

    resolved_case_ids = _batch_resolve_case_ids(db, events, parsed_meta)
    for cid in resolved_case_ids:
        if cid:
            case_ids.add(cid)

    cases: dict[str, Case] = {}
    if case_ids:
        uuids = []
        for cid in case_ids:
            try:
                uuids.append(uuid.UUID(cid))
            except ValueError:
                continue
        if uuids:
            rows = db.execute(select(Case).where(Case.id.in_(uuids))).scalars().all()
            cases = {str(c.id): c for c in rows}

    out: list[AdminAuditEventOut] = []
    for e, meta, cid in zip(events, parsed_meta, resolved_case_ids):
        actor = users.get(e.actor_user_id) if e.actor_user_id else None
        case = cases.get(cid) if cid else None
        out.append(
            AdminAuditEventOut(
                id=str(e.id),
                actor_user_id=str(e.actor_user_id) if e.actor_user_id else None,
                actor_display_name=actor.display_name if actor else None,
                actor_initials=actor.initials if actor else None,
                action=e.action,
                summary=format_audit_summary(
                    action=e.action,
                    entity_type=e.entity_type,
                    entity_id=e.entity_id,
                    meta=meta,
                ),
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                case_id=cid,
                case_number=case.case_number if case else None,
                case_title=case.title if case else None,
                ip=e.ip,
                user_agent=e.user_agent,
                meta=meta,
                created_at=e.created_at,
            )
        )
    return out


@router.get("", response_model=list[AdminAuditEventOut])
def list_audit_events(
    action: str | None = None,
    action_prefix: str | None = Query(default=None, description="Filter actions starting with this prefix"),
    accounts_only: bool = Query(default=False, description="Ledger postings and invoice lifecycle only"),
    actor_user_id: uuid.UUID | None = None,
    case_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    since: str | None = Query(default=None, description="ISO 8601 datetime"),
    until: str | None = Query(default=None, description="ISO 8601 datetime"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminAuditEventOut]:
    del admin  # access gate only

    since_dt = _parse_dt(since)
    until_dt = _parse_dt(until)

    clauses = []
    if accounts_only:
        clauses.append(AuditEvent.action.in_(ACCOUNTS_AUDIT_ACTIONS))
    elif action:
        clauses.append(AuditEvent.action == action)
    elif action_prefix:
        clauses.append(AuditEvent.action.like(f"{action_prefix}%"))
    if actor_user_id:
        clauses.append(AuditEvent.actor_user_id == actor_user_id)
    if case_id:
        clauses.append(_case_id_filter(db, case_id))
    if entity_type:
        clauses.append(AuditEvent.entity_type == entity_type)
    if entity_id:
        clauses.append(AuditEvent.entity_id == entity_id)
    if since_dt:
        clauses.append(AuditEvent.created_at >= since_dt)
    if until_dt:
        clauses.append(AuditEvent.created_at <= until_dt)

    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    if clauses:
        stmt = stmt.where(and_(*clauses))

    events = db.execute(stmt).scalars().all()
    return _serialize_events(db, events)

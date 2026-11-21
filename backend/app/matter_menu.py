"""Bounded, firm-wide menu queries. Opening a matter still checks access separately."""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.list_search import _ilike_pattern, reject_search_nul
from app.models import Case, CaseSource, CaseStatus, MatterHeadType, MatterSubType, User

SortKey = Literal['reference', 'client', 'matter', 'feeEarner', 'status', 'source', 'created']
Direction = Literal['asc', 'desc']
Menu = Literal['main', 'quotes']


def expressions():
    stored_reference = func.regexp_replace(func.btrim(Case.case_number), '^[Qq]([0-9])', r'\1')
    reference = case((Case.status == CaseStatus.quote, literal('Q') + stored_reference), else_=stored_reference)
    staff = func.coalesce(User.display_name, '—')
    source = func.coalesce(CaseSource.name, '')
    status = cast(Case.status, String)
    status_label = case({'open': 'Active', 'post_completion': 'Post-completion', 'closed': 'Closed',
                         'quote_closed': 'Closed', 'archived': 'Archived', 'quote': 'Quote'}, value=status, else_=status)
    head = func.coalesce(MatterHeadType.name, Case.matter_head_type_name, '')
    sub = func.coalesce(MatterSubType.name, Case.matter_sub_type_name, '')
    matter_type = case((and_(head != '', sub != ''), head + ' · ' + sub),
                       (head != '', head), (sub != '', sub), else_='—')
    fields = {'reference': reference, 'client': func.coalesce(Case.client_name, ''),
              'matter': func.coalesce(Case.title, ''), 'feeEarner': staff, 'status': status,
              'source': source, 'created': Case.created_at}
    search = reference + ' ' + fields['client'] + ' ' + fields['matter'] + ' ' + status_label + ' ' + staff + ' ' + source
    return fields, matter_type, search


def joined(stmt):
    return (stmt.outerjoin(User, and_(Case.fee_earner_user_id == User.id, User.is_active.is_(True)))
            .outerjoin(CaseSource, Case.source_id == CaseSource.id)
            .outerjoin(MatterSubType, Case.matter_sub_type_id == MatterSubType.id)
            .outerjoin(MatterHeadType, MatterHeadType.id == case(
                (MatterSubType.id.isnot(None), MatterSubType.head_type_id), else_=Case.matter_head_type_id)))


def menu_condition(menu):
    quotes = Case.status.in_([CaseStatus.quote, CaseStatus.quote_closed])
    return quotes if menu == 'quotes' else ~quotes


def matter_type_options(db: Session):
    _, matter_type, _ = expressions()
    return list(db.scalars(joined(select(matter_type).select_from(Case)).distinct().order_by(matter_type)))


def menu_page(db: Session, *, q='', menu: Menu='main', sort: SortKey='created', direction: Direction='desc',
              matter_types=(), fee_earners=(), statuses=(), cursor=None, limit=100):
    q = q.strip().lower()
    reject_search_nul(q)
    fields, matter_type, search = expressions()
    # ICU root collation matches the browser's usual localeCompare ordering (including accents/case).
    key = fields[sort] if sort == 'created' else fields[sort].collate('und-x-icu')
    signature = hashlib.sha256(json.dumps([q, menu, sort, direction, sorted(matter_types),
        sorted(str(x) for x in fee_earners), sorted(str(x) for x in statuses)], separators=(',', ':')).encode()).hexdigest()
    stmt = joined(select(Case, key.label('sort_value'))).where(menu_condition(menu))
    if q:
        # Preserve the menu's literal substring search and search-overrides-filters behaviour.
        stmt = stmt.where(func.lower(search).like(_ilike_pattern(q), escape='\\'))
    else:
        if matter_types: stmt = stmt.where(matter_type.in_(matter_types))
        if fee_earners: stmt = stmt.where(Case.fee_earner_user_id.in_(fee_earners))
        if statuses: stmt = stmt.where(Case.status.in_(statuses))
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if value['query'] != signature: raise ValueError()
            boundary = datetime.fromisoformat(value['value']) if sort == 'created' else value['value']
            if not isinstance(boundary, (str, datetime)): raise ValueError()
            created = datetime.fromisoformat(value['created'])
            identifier = uuid.UUID(value['id'])
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(400, 'Invalid matter list cursor. Refresh the list.') from None
        beyond = key > boundary if direction == 'asc' else key < boundary
        stmt = stmt.where(or_(beyond, and_(key == boundary, or_(Case.created_at < created,
                      and_(Case.created_at == created, Case.id > identifier)))))
    stmt = stmt.order_by(key.asc() if direction == 'asc' else key.desc(), Case.created_at.desc(), Case.id.asc()).limit(limit + 1)
    rows = db.execute(stmt).all()
    next_cursor = None
    if len(rows) > limit:
        last, value = rows[limit-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps({'query': signature, 'value': value.isoformat() if isinstance(value, datetime) else value,
            'created': last.created_at.isoformat(), 'id': str(last.id)}, separators=(',', ':')).encode()).decode()
    return [row[0] for row in rows[:limit]], next_cursor

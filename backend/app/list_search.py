"""Server-side search helpers for contacts and cases."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.deps import get_case_if_accessible
from app.models import Case, CaseStatus, Contact, ContactType, User

CONTACT_SEARCH_DEFAULT_LIMIT = 25
CONTACT_SEARCH_MAX_LIMIT = 200
CASE_SEARCH_DEFAULT_LIMIT = 50
CASE_SEARCH_MAX_LIMIT = 100


def _ilike_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search_contacts(
    db: Session,
    *,
    q: str | None = None,
    limit: int | None = None,
    type_filter: ContactType | None = None,
    has_email: bool | None = None,
    has_phone: bool | None = None,
) -> list[Contact]:
    stmt = select(Contact)
    if type_filter is not None:
        stmt = stmt.where(Contact.type == type_filter)
    if has_email is True:
        stmt = stmt.where(Contact.email.isnot(None), Contact.email != "")
    elif has_email is False:
        stmt = stmt.where(or_(Contact.email.is_(None), Contact.email == ""))
    if has_phone is True:
        stmt = stmt.where(Contact.phone.isnot(None), Contact.phone != "")
    elif has_phone is False:
        stmt = stmt.where(or_(Contact.phone.is_(None), Contact.phone == ""))

    q_trim = (q or "").strip()
    if q_trim:
        pat = _ilike_pattern(q_trim)
        stmt = stmt.where(
            or_(
                Contact.name.ilike(pat),
                Contact.email.ilike(pat),
                Contact.phone.ilike(pat),
                Contact.company_name.ilike(pat),
                Contact.trading_name.ilike(pat),
                Contact.first_name.ilike(pat),
                Contact.last_name.ilike(pat),
                Contact.postcode.ilike(pat),
            )
        )
        cap = min(limit or CONTACT_SEARCH_DEFAULT_LIMIT, CONTACT_SEARCH_MAX_LIMIT)
        stmt = stmt.order_by(Contact.name.asc()).limit(cap)
    else:
        stmt = stmt.order_by(Contact.name.asc())
        if limit is not None:
            stmt = stmt.limit(min(limit, CONTACT_SEARCH_MAX_LIMIT))

    return list(db.execute(stmt).scalars().all())


def search_cases(
    db: Session,
    user: User,
    *,
    q: str,
    limit: int | None = None,
    status_filter: CaseStatus | None = None,
) -> list[Case]:
    q_trim = q.strip()
    if not q_trim:
        return []

    pat = _ilike_pattern(q_trim)
    cap = min(limit or CASE_SEARCH_DEFAULT_LIMIT, CASE_SEARCH_MAX_LIMIT)
    fetch_cap = min(cap * 3, CASE_SEARCH_MAX_LIMIT * 3)

    stmt = (
        select(Case)
        .outerjoin(User, Case.fee_earner_user_id == User.id)
        .where(
            or_(
                Case.case_number.ilike(pat),
                Case.client_name.ilike(pat),
                Case.title.ilike(pat),
                User.display_name.ilike(pat),
                User.initials.ilike(pat),
            )
        )
        .order_by(Case.case_number.desc())
        .limit(fetch_cap)
    )
    if status_filter is not None:
        stmt = stmt.where(Case.status == status_filter)

    rows = list(db.execute(stmt).scalars().all())
    out: list[Case] = []
    for case in rows:
        if get_case_if_accessible(case.id, user, db) is None:
            continue
        out.append(case)
        if len(out) >= cap:
            break
    return out

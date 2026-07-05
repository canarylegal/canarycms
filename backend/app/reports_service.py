"""Reporting queries: firm-wide aggregates with fee-earner scope and non-admin restrictions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import case as sql_case, func, select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.case_reference import display_case_number
from app.permission_checks import user_may_access_accounts_workspace, user_may_be_fee_earner
from app.invoice_service import INV_APPROVED, INV_PENDING
from app.models import (
    Case,
    CaseEvent,
    CaseInvoice,
    CaseInvoiceLine,
    CaseSource,
    CaseStatus,
    LedgerAccount,
    LedgerAccountType,
    LedgerDirection,
    LedgerEntry,
    MatterSubTypeEventTemplate,
    User,
)


def _utc_day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _utc_day_end_exclusive(d: date) -> datetime:
    return _utc_day_start(d) + timedelta(days=1)


def enforce_fee_earner_ids(user: User, db: Session, requested: list[uuid.UUID]) -> list[uuid.UUID]:
    if not requested:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one fee earner.")
    uniq = list(dict.fromkeys(requested))
    if user_effective_admin(user, db) or user_may_access_accounts_workspace(user, db):
        for uid in uniq:
            u = db.get(User, uid)
            if not u or not u.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One of the selected fee earners is unknown or inactive.",
                )
            if not user_may_be_fee_earner(u, db):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One of the selected users is not permitted to act as a fee earner.",
                )
        return uniq
    if not user_may_be_fee_earner(user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your permission profile does not allow fee-earner reporting.",
        )
    if set(uniq) != {user.id}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only run reports for matters where you are the fee earner.",
        )
    u = db.get(User, user.id)
    if not u or not u.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your user account is inactive.")
    return uniq


def list_fee_earner_pick_users(user: User, db: Session) -> list[User]:
    if user_effective_admin(user, db) or user_may_access_accounts_workspace(user, db):
        rows = db.execute(select(User).where(User.is_active.is_(True)).order_by(User.display_name.asc())).scalars().all()
        return [u for u in rows if user_may_be_fee_earner(u, db)]
    if user_may_be_fee_earner(user, db):
        return [user]
    return []


def _signed_amount_expr():
    return func.sum(
        sql_case(
            (LedgerEntry.direction == LedgerDirection.credit, LedgerEntry.amount_pence),
            else_=-LedgerEntry.amount_pence,
        )
    )


def balances_by_case_ids(case_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, tuple[int, int]]:
    """Return ``case_id -> (client_pence, office_pence)`` for approved ledger entries only."""
    if not case_ids:
        return {}
    signed = _signed_amount_expr()
    rows = (
        db.execute(
            select(LedgerAccount.case_id, LedgerAccount.account_type, signed)
            .select_from(LedgerAccount)
            .outerjoin(
                LedgerEntry,
                (LedgerAccount.id == LedgerEntry.account_id) & (LedgerEntry.is_approved.is_(True)),
            )
            .where(LedgerAccount.case_id.in_(case_ids))
            .group_by(LedgerAccount.case_id, LedgerAccount.account_type)
        )
        .all()
    )
    merged: dict[uuid.UUID, dict[str, int]] = {cid: {"client": 0, "office": 0} for cid in case_ids}
    for case_id, atype, bal in rows:
        b = 0 if bal is None else int(bal)
        if atype == LedgerAccountType.client:
            merged[case_id]["client"] = b
        elif atype == LedgerAccountType.office:
            merged[case_id]["office"] = b
    return {cid: (merged[cid]["client"], merged[cid]["office"]) for cid in case_ids}


def _fee_earner_label(db: Session, user_id: uuid.UUID | None) -> str:
    if not user_id:
        return ""
    u = db.get(User, user_id)
    if not u:
        return ""
    return (u.display_name or u.email or "").strip()


def _case_status_label(s: CaseStatus) -> str:
    if s == CaseStatus.open:
        return "Active"
    if s == CaseStatus.quote:
        return "Quote"
    if s == CaseStatus.quote_closed:
        return "Closed quote"
    if s == CaseStatus.closed:
        return "Closed"
    if s == CaseStatus.archived:
        return "Archived"
    if s == CaseStatus.post_completion:
        return "Post-completion"
    return s.value


@dataclass
class ClientOfficeBalanceRow:
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_user_id: uuid.UUID | None
    fee_earner_name: str
    client_balance_pence: int
    office_balance_pence: int


def report_client_office_balances(
    fee_earner_user_ids: list[uuid.UUID], db: Session
) -> tuple[list[ClientOfficeBalanceRow], dict[str, int]]:
    rows = (
        db.execute(
            select(Case)
            .where(
                Case.fee_earner_user_id.in_(fee_earner_user_ids),
                Case.fee_earner_user_id.isnot(None),
                Case.status.notin_((CaseStatus.closed, CaseStatus.archived, CaseStatus.quote_closed)),
            )
            .order_by(Case.case_number.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return [], {"client_balance_pence": 0, "office_balance_pence": 0}
    case_ids = [c.id for c in rows]
    bal = balances_by_case_ids(case_ids, db)
    out: list[ClientOfficeBalanceRow] = []
    tot_client = tot_office = 0
    for c in rows:
        cp, op = bal.get(c.id, (0, 0))
        tot_client += cp
        tot_office += op
        out.append(
            ClientOfficeBalanceRow(
                case_id=c.id,
                case_number=display_case_number(c.case_number, c.status),
                client_name=c.client_name,
                matter_description=c.title,
                fee_earner_user_id=c.fee_earner_user_id,
                fee_earner_name=_fee_earner_label(db, c.fee_earner_user_id),
                client_balance_pence=cp,
                office_balance_pence=op,
            )
        )
    totals = {"client_balance_pence": tot_client, "office_balance_pence": tot_office}
    return out, totals


def _invoice_line_split(lines: list[CaseInvoiceLine]) -> tuple[int, int, int]:
    """Return (fees_ex_vat_pence, vat_pence, disbursements_ex_vat_pence)."""
    fees = 0
    vat = 0
    disb = 0
    for ln in lines:
        if ln.line_type == "fee":
            fees += int(ln.amount_pence)
            vat += int(ln.tax_pence)
        elif ln.line_type == "disbursement":
            disb += int(ln.amount_pence)
            vat += int(ln.tax_pence)
        elif ln.line_type == "vat":
            vat += int(ln.amount_pence)
    return fees, vat, disb


@dataclass
class BillingReportRow:
    invoice_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    invoice_number: str
    invoice_status: str
    fee_earner_name: str
    created_at: datetime
    fees_ex_vat_pence: int
    vat_pence: int
    disbursements_ex_vat_pence: int


def report_billing(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[BillingReportRow], dict[str, int]]:
    q = (
        select(CaseInvoice, Case)
        .join(Case, Case.id == CaseInvoice.case_id)
        .where(
            Case.fee_earner_user_id.in_(fee_earner_user_ids),
            Case.fee_earner_user_id.isnot(None),
            CaseInvoice.status.in_((INV_PENDING, INV_APPROVED)),
        )
        .order_by(CaseInvoice.created_at.desc())
    )
    if date_from is not None:
        q = q.where(CaseInvoice.created_at >= _utc_day_start(date_from))
    if date_to is not None:
        q = q.where(CaseInvoice.created_at < _utc_day_end_exclusive(date_to))
    pairs = db.execute(q).all()
    out: list[BillingReportRow] = []
    tot_f = tot_v = tot_d = 0
    for inv, case in pairs:
        lines = (
            db.execute(select(CaseInvoiceLine).where(CaseInvoiceLine.invoice_id == inv.id))
            .scalars()
            .all()
        )
        f, v, d = _invoice_line_split(lines)
        tot_f += f
        tot_v += v
        tot_d += d
        out.append(
            BillingReportRow(
                invoice_id=inv.id,
                case_id=case.id,
                case_number=display_case_number(case.case_number, case.status),
                client_name=case.client_name,
                invoice_number=inv.invoice_number,
                invoice_status=inv.status,
                fee_earner_name=_fee_earner_label(db, case.fee_earner_user_id),
                created_at=inv.created_at,
                fees_ex_vat_pence=f,
                vat_pence=v,
                disbursements_ex_vat_pence=d,
            )
        )
    totals = {
        "fees_ex_vat_pence": tot_f,
        "vat_pence": tot_v,
        "disbursements_ex_vat_pence": tot_d,
    }
    return out, totals


@dataclass
class CaseReportRow:
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    status: str
    status_label: str
    fee_earner_name: str
    source_name: str | None
    created_at: datetime


def _source_names_for_cases(cases: list[Case], db: Session) -> dict[uuid.UUID, str]:
    ids = {c.source_id for c in cases if c.source_id}
    if not ids:
        return {}
    rows = db.execute(select(CaseSource).where(CaseSource.id.in_(ids))).scalars().all()
    return {s.id: s.name for s in rows}


def report_cases(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    statuses: list[CaseStatus] | None = None,
) -> list[CaseReportRow]:
    q = select(Case).where(
        Case.fee_earner_user_id.in_(fee_earner_user_ids),
        Case.fee_earner_user_id.isnot(None),
    )
    if statuses:
        q = q.where(Case.status.in_(statuses))
    rows = db.execute(q.order_by(Case.case_number.asc())).scalars().all()
    source_map = _source_names_for_cases(rows, db)
    return [
        CaseReportRow(
            case_id=c.id,
            case_number=display_case_number(c.case_number, c.status),
            client_name=c.client_name,
            matter_description=c.title,
            status=c.status.value,
            status_label=_case_status_label(c.status),
            fee_earner_name=_fee_earner_label(db, c.fee_earner_user_id),
            source_name=source_map.get(c.source_id) if c.source_id else None,
            created_at=c.created_at,
        )
        for c in rows
    ]


def report_cases_opened(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    date_from: date,
    date_to: date,
    include_quote: bool,
    include_active: bool,
) -> list[CaseReportRow]:
    if not include_quote and not include_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one of Quote or Active for new files.",
        )
    st: list[CaseStatus] = []
    if include_quote:
        st.append(CaseStatus.quote)
    if include_active:
        st.append(CaseStatus.open)
    q = (
        select(Case)
        .where(
            Case.fee_earner_user_id.in_(fee_earner_user_ids),
            Case.fee_earner_user_id.isnot(None),
            Case.status.in_(st),
            Case.created_at >= _utc_day_start(date_from),
            Case.created_at < _utc_day_end_exclusive(date_to),
        )
        .order_by(Case.created_at.desc())
    )
    rows = db.execute(q).scalars().all()
    source_map = _source_names_for_cases(rows, db)
    return [
        CaseReportRow(
            case_id=c.id,
            case_number=display_case_number(c.case_number, c.status),
            client_name=c.client_name,
            matter_description=c.title,
            status=c.status.value,
            status_label=_case_status_label(c.status),
            fee_earner_name=_fee_earner_label(db, c.fee_earner_user_id),
            source_name=source_map.get(c.source_id) if c.source_id else None,
            created_at=c.created_at,
        )
        for c in rows
    ]


@dataclass
class EventsReportRow:
    event_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    matter_description: str
    fee_earner_name: str
    event_name: str
    event_date: date | None
    template_id: uuid.UUID | None
    event_category: str | None


def report_events(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    template_ids: list[uuid.UUID] | None = None,
) -> list[EventsReportRow]:
    q = (
        select(CaseEvent, Case)
        .join(Case, Case.id == CaseEvent.case_id)
        .where(
            Case.fee_earner_user_id.in_(fee_earner_user_ids),
            Case.fee_earner_user_id.isnot(None),
        )
        .order_by(
            sql_case((CaseEvent.event_date.is_(None), 1), else_=0),
            CaseEvent.event_date.desc(),
            Case.case_number.asc(),
            CaseEvent.sort_order,
        )
    )
    if template_ids is not None and len(template_ids) > 0:
        q = q.where(CaseEvent.template_id.in_(template_ids))
    if date_from is not None or date_to is not None:
        q = q.where(CaseEvent.event_date.isnot(None))
        if date_from is not None:
            q = q.where(CaseEvent.event_date >= date_from)
        if date_to is not None:
            q = q.where(CaseEvent.event_date <= date_to)
    pairs = db.execute(q).all()
    tmpl_names: dict[uuid.UUID, str] = {}
    tids = {e.template_id for e, _c in pairs if e.template_id}
    if tids:
        trows = db.execute(select(MatterSubTypeEventTemplate).where(MatterSubTypeEventTemplate.id.in_(tids))).scalars().all()
        tmpl_names = {t.id: t.name for t in trows}
    out: list[EventsReportRow] = []
    for e, c in pairs:
        cat = tmpl_names.get(e.template_id) if e.template_id else None
        out.append(
            EventsReportRow(
                event_id=e.id,
                case_id=c.id,
                case_number=display_case_number(c.case_number, c.status),
                matter_description=c.title,
                fee_earner_name=_fee_earner_label(db, c.fee_earner_user_id),
                event_name=e.name,
                event_date=e.event_date,
                template_id=e.template_id,
                event_category=cat,
            )
        )
    return out


@dataclass
class LedgerActivityRow:
    pair_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_name: str
    posted_at: datetime
    posted_by_name: str
    description: str
    reference: str | None
    amount_pence: int
    client_direction: str | None
    office_direction: str | None
    is_approved: bool
    contact_label: str | None


def report_ledger_activity(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    approved_only: bool = False,
) -> list[LedgerActivityRow]:
    q = (
        select(LedgerEntry, LedgerAccount, Case, User)
        .join(LedgerAccount, LedgerEntry.account_id == LedgerAccount.id)
        .join(Case, LedgerAccount.case_id == Case.id)
        .outerjoin(User, LedgerEntry.posted_by_user_id == User.id)
        .where(
            Case.fee_earner_user_id.in_(fee_earner_user_ids),
            Case.fee_earner_user_id.isnot(None),
        )
        .order_by(LedgerEntry.posted_at.desc(), Case.case_number.asc())
    )
    if date_from is not None:
        q = q.where(LedgerEntry.posted_at >= _utc_day_start(date_from))
    if date_to is not None:
        q = q.where(LedgerEntry.posted_at < _utc_day_end_exclusive(date_to))
    if approved_only:
        q = q.where(LedgerEntry.is_approved.is_(True))

    rows = db.execute(q).all()
    by_pair: dict[uuid.UUID, dict] = {}
    for entry, account, case, poster in rows:
        pid = entry.pair_id
        bucket = by_pair.get(pid)
        if bucket is None:
            poster_name = _fee_earner_label(db, entry.posted_by_user_id) if entry.posted_by_user_id else "—"
            if poster and poster.display_name:
                poster_name = poster.display_name.strip() or poster.email
            bucket = {
                "pair_id": pid,
                "case_id": case.id,
                "case_number": display_case_number(case.case_number, case.status),
                "client_name": case.client_name,
                "matter_description": case.title,
                "fee_earner_name": _fee_earner_label(db, case.fee_earner_user_id),
                "posted_at": entry.posted_at,
                "posted_by_name": poster_name,
                "description": entry.description or "",
                "reference": entry.reference,
                "amount_pence": int(entry.amount_pence),
                "client_direction": None,
                "office_direction": None,
                "is_approved": entry.is_approved,
                "contact_label": entry.contact_label,
            }
            by_pair[pid] = bucket
        else:
            if entry.is_approved:
                bucket["is_approved"] = True
            if entry.contact_label and not bucket.get("contact_label"):
                bucket["contact_label"] = entry.contact_label
        if account.account_type == LedgerAccountType.client:
            bucket["client_direction"] = entry.direction.value
        elif account.account_type == LedgerAccountType.office:
            bucket["office_direction"] = entry.direction.value

    out: list[LedgerActivityRow] = []
    for b in by_pair.values():
        out.append(LedgerActivityRow(**b))
    out.sort(key=lambda r: (r.posted_at, r.case_number), reverse=True)
    return out


def _age_bucket_label(age_days: int) -> str:
    if age_days <= 30:
        return "0-30"
    if age_days <= 60:
        return "31-60"
    if age_days <= 90:
        return "61-90"
    return "90+"


def _as_utc_date(dt: datetime) -> date:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).date()
    return dt.date()


@dataclass
class AgedDebtRow:
    invoice_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_name: str
    invoice_number: str
    approved_at: datetime
    age_days: int
    age_bucket: str
    invoice_total_pence: int
    office_balance_pence: int


def report_aged_debt(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    as_of: date | None = None,
) -> tuple[list[AgedDebtRow], dict[str, int]]:
    """Approved invoices on matters whose office balance is still debit (client owes).

    Age is measured from ``approved_at`` (fallback ``created_at``). There is no separate
    paid flag — matter office balance is the debt indicator.
    """
    ref = as_of or datetime.now(timezone.utc).date()
    pairs = (
        db.execute(
            select(CaseInvoice, Case)
            .join(Case, Case.id == CaseInvoice.case_id)
            .where(
                Case.fee_earner_user_id.in_(fee_earner_user_ids),
                Case.fee_earner_user_id.isnot(None),
                CaseInvoice.status == INV_APPROVED,
            )
            .order_by(CaseInvoice.approved_at.desc().nullslast(), CaseInvoice.created_at.desc())
        )
        .all()
    )
    if not pairs:
        return [], {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    case_ids = list({c.id for _inv, c in pairs})
    bal = balances_by_case_ids(case_ids, db)
    out: list[AgedDebtRow] = []
    bucket_totals = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for inv, case in pairs:
        _client, office = bal.get(case.id, (0, 0))
        if office >= 0:
            continue
        anchor = inv.approved_at or inv.created_at
        age_days = max(0, (ref - _as_utc_date(anchor)).days)
        bucket = _age_bucket_label(age_days)
        total = int(inv.total_pence)
        bucket_totals[bucket] += total
        out.append(
            AgedDebtRow(
                invoice_id=inv.id,
                case_id=case.id,
                case_number=display_case_number(case.case_number, case.status),
                client_name=case.client_name,
                matter_description=case.title,
                fee_earner_name=_fee_earner_label(db, case.fee_earner_user_id),
                invoice_number=inv.invoice_number,
                approved_at=anchor,
                age_days=age_days,
                age_bucket=bucket,
                invoice_total_pence=total,
                office_balance_pence=office,
            )
        )
    out.sort(key=lambda r: (r.age_days, r.case_number), reverse=True)
    return out, bucket_totals


@dataclass
class PendingLedgerApprovalRow:
    pair_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_name: str
    posted_at: datetime
    posted_by_user_id: uuid.UUID | None
    posted_by_name: str
    description: str
    amount_pence: int
    client_direction: str | None
    office_direction: str | None
    is_anticipated: bool
    anticipated_for_date: date | None
    reference: str | None


@dataclass
class PendingInvoiceRow:
    invoice_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_name: str
    invoice_number: str
    created_at: datetime
    total_pence: int


@dataclass
class CaseBalanceExceptionRow:
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    status: str
    status_label: str
    fee_earner_name: str
    client_balance_pence: int
    office_balance_pence: int


@dataclass
class LargePostingRow:
    pair_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_name: str
    posted_at: datetime
    posted_by_name: str
    description: str
    amount_pence: int
    client_direction: str | None
    office_direction: str | None
    is_approved: bool


@dataclass
class ExceptionsReport:
    pending_ledger_approvals: list[PendingLedgerApprovalRow]
    pending_invoices: list[PendingInvoiceRow]
    client_balance_closed_archived: list[CaseBalanceExceptionRow]
    negative_client_balance: list[CaseBalanceExceptionRow]
    large_postings: list[LargePostingRow]


def _pending_ledger_approvals(
    fee_earner_user_ids: list[uuid.UUID], db: Session
) -> list[PendingLedgerApprovalRow]:
    rows = (
        db.execute(
            select(LedgerEntry, LedgerAccount, Case, User)
            .join(LedgerAccount, LedgerEntry.account_id == LedgerAccount.id)
            .join(Case, LedgerAccount.case_id == Case.id)
            .outerjoin(User, LedgerEntry.posted_by_user_id == User.id)
            .where(
                Case.fee_earner_user_id.in_(fee_earner_user_ids),
                Case.fee_earner_user_id.isnot(None),
                LedgerEntry.is_approved.is_(False),
            )
            .order_by(LedgerEntry.posted_at.desc())
        )
        .all()
    )
    by_pair: dict[uuid.UUID, dict] = {}
    for entry, account, case, poster in rows:
        pid = entry.pair_id
        bucket = by_pair.get(pid)
        if bucket is None:
            poster_name = "—"
            if poster and (poster.display_name or poster.email):
                poster_name = (poster.display_name or poster.email or "").strip()
            bucket = {
                "pair_id": pid,
                "case_id": case.id,
                "case_number": display_case_number(case.case_number, case.status),
                "client_name": case.client_name,
                "matter_description": case.title,
                "fee_earner_name": _fee_earner_label(db, case.fee_earner_user_id),
                "posted_at": entry.posted_at,
                "posted_by_user_id": entry.posted_by_user_id,
                "posted_by_name": poster_name,
                "description": entry.description or "",
                "amount_pence": int(entry.amount_pence),
                "reference": entry.reference,
                "client_direction": None,
                "office_direction": None,
                "is_anticipated": bool(entry.is_anticipated),
                "anticipated_for_date": entry.anticipated_for_date,
            }
            by_pair[pid] = bucket
        if account.account_type == LedgerAccountType.client:
            bucket["client_direction"] = entry.direction.value
        elif account.account_type == LedgerAccountType.office:
            bucket["office_direction"] = entry.direction.value
    out = [PendingLedgerApprovalRow(**b) for b in by_pair.values()]
    out.sort(key=lambda r: r.posted_at, reverse=True)
    return out


def _pending_invoices(fee_earner_user_ids: list[uuid.UUID], db: Session) -> list[PendingInvoiceRow]:
    pairs = (
        db.execute(
            select(CaseInvoice, Case)
            .join(Case, Case.id == CaseInvoice.case_id)
            .where(
                Case.fee_earner_user_id.in_(fee_earner_user_ids),
                Case.fee_earner_user_id.isnot(None),
                CaseInvoice.status == INV_PENDING,
            )
            .order_by(CaseInvoice.created_at.desc())
        )
        .all()
    )
    return [
        PendingInvoiceRow(
            invoice_id=inv.id,
            case_id=case.id,
            case_number=display_case_number(case.case_number, case.status),
            client_name=case.client_name,
            matter_description=case.title,
            fee_earner_name=_fee_earner_label(db, case.fee_earner_user_id),
            invoice_number=inv.invoice_number,
            created_at=inv.created_at,
            total_pence=int(inv.total_pence),
        )
        for inv, case in pairs
    ]


def _case_balance_exceptions(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    statuses: list[CaseStatus] | None,
    client_balance_filter: str,
) -> list[CaseBalanceExceptionRow]:
    q = select(Case).where(
        Case.fee_earner_user_id.in_(fee_earner_user_ids),
        Case.fee_earner_user_id.isnot(None),
    )
    if statuses is not None:
        q = q.where(Case.status.in_(statuses))
    cases = db.execute(q.order_by(Case.case_number.asc())).scalars().all()
    if not cases:
        return []
    bal = balances_by_case_ids([c.id for c in cases], db)
    out: list[CaseBalanceExceptionRow] = []
    for case in cases:
        client, office = bal.get(case.id, (0, 0))
        if client_balance_filter == "nonzero_closed" and client == 0:
            continue
        if client_balance_filter == "negative" and client >= 0:
            continue
        out.append(
            CaseBalanceExceptionRow(
                case_id=case.id,
                case_number=display_case_number(case.case_number, case.status),
                client_name=case.client_name,
                matter_description=case.title,
                status=case.status.value,
                status_label=_case_status_label(case.status),
                fee_earner_name=_fee_earner_label(db, case.fee_earner_user_id),
                client_balance_pence=client,
                office_balance_pence=office,
            )
        )
    return out


def _large_postings(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    min_amount_pence: int,
) -> list[LargePostingRow]:
    q = (
        select(LedgerEntry, LedgerAccount, Case, User)
        .join(LedgerAccount, LedgerEntry.account_id == LedgerAccount.id)
        .join(Case, LedgerAccount.case_id == Case.id)
        .outerjoin(User, LedgerEntry.posted_by_user_id == User.id)
        .where(
            Case.fee_earner_user_id.in_(fee_earner_user_ids),
            Case.fee_earner_user_id.isnot(None),
            LedgerEntry.amount_pence >= min_amount_pence,
        )
        .order_by(LedgerEntry.posted_at.desc())
    )
    if date_from is not None:
        q = q.where(LedgerEntry.posted_at >= _utc_day_start(date_from))
    if date_to is not None:
        q = q.where(LedgerEntry.posted_at < _utc_day_end_exclusive(date_to))
    rows = db.execute(q).all()
    by_pair: dict[uuid.UUID, dict] = {}
    for entry, account, case, poster in rows:
        pid = entry.pair_id
        bucket = by_pair.get(pid)
        if bucket is None:
            poster_name = "—"
            if poster and (poster.display_name or poster.email):
                poster_name = (poster.display_name or poster.email or "").strip()
            bucket = {
                "pair_id": pid,
                "case_id": case.id,
                "case_number": display_case_number(case.case_number, case.status),
                "client_name": case.client_name,
                "matter_description": case.title,
                "fee_earner_name": _fee_earner_label(db, case.fee_earner_user_id),
                "posted_at": entry.posted_at,
                "posted_by_name": poster_name,
                "description": entry.description or "",
                "amount_pence": int(entry.amount_pence),
                "client_direction": None,
                "office_direction": None,
                "is_approved": entry.is_approved,
            }
            by_pair[pid] = bucket
        else:
            if entry.is_approved:
                bucket["is_approved"] = True
        if account.account_type == LedgerAccountType.client:
            bucket["client_direction"] = entry.direction.value
        elif account.account_type == LedgerAccountType.office:
            bucket["office_direction"] = entry.direction.value
    out = [LargePostingRow(**b) for b in by_pair.values()]
    out.sort(key=lambda r: r.posted_at, reverse=True)
    return out


def report_exceptions(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    large_posting_min_pence: int = 500_000,
) -> ExceptionsReport:
    return ExceptionsReport(
        pending_ledger_approvals=_pending_ledger_approvals(fee_earner_user_ids, db),
        pending_invoices=_pending_invoices(fee_earner_user_ids, db),
        client_balance_closed_archived=_case_balance_exceptions(
            fee_earner_user_ids,
            db,
            statuses=[CaseStatus.closed, CaseStatus.archived],
            client_balance_filter="nonzero_closed",
        ),
        negative_client_balance=_case_balance_exceptions(
            fee_earner_user_ids,
            db,
            statuses=None,
            client_balance_filter="negative",
        ),
        large_postings=_large_postings(
            fee_earner_user_ids,
            db,
            date_from=date_from,
            date_to=date_to,
            min_amount_pence=large_posting_min_pence,
        ),
    )


def pence_to_pounds_str(p: int) -> str:
    neg = p < 0
    a = abs(p)
    main = a // 100
    frac = a % 100
    s = f"{main}.{frac:02d}"
    return f"-{s}" if neg else s


def rows_to_workbook(sheet_title: str, headers: list[str], row_values: list[list[Any]]) -> Any:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31] if sheet_title else "Report"
    ws.append(headers)
    for rv in row_values:
        ws.append(rv)
    return wb

"""Case time entry helpers (6-minute units, charge rate valuation, WIP billing)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.billing_service import get_billing_settings
from app.models import Case, CaseInvoiceLine, CaseTimeEntry, CaseTimeEntryStatus, User
from app.schemas import CaseInvoiceLineCreate

TIME_UNIT_MINUTES = 6


def validate_duration_minutes(duration_minutes: int) -> None:
    if duration_minutes < TIME_UNIT_MINUTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Duration must be at least {TIME_UNIT_MINUTES} minutes (0.1 hour).",
        )
    if duration_minutes % TIME_UNIT_MINUTES != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Duration must be in {TIME_UNIT_MINUTES}-minute (0.1 hour) units.",
        )


def time_entry_value_pence(duration_minutes: int, charge_rate_pence_per_hour: int | None) -> int | None:
    if not charge_rate_pence_per_hour or charge_rate_pence_per_hour <= 0:
        return None
    return round(duration_minutes * charge_rate_pence_per_hour / 60)


def user_has_charge_rate(user: User | None) -> bool:
    return bool(user and user.charge_rate_pence_per_hour and user.charge_rate_pence_per_hour > 0)


def resolve_non_billable(*, non_billable: bool, target_user: User) -> bool:
    """Billable time requires a charge rate; otherwise non_billable must be explicit."""
    if user_has_charge_rate(target_user):
        return non_billable
    if not non_billable:
        name = (target_user.display_name or target_user.email or "This fee earner").strip()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{name} has no charge rate. Record as non-billable (nil rate), "
                "or ask an admin to set a charge rate under Admin → Users."
            ),
        )
    return True


def entry_billable_value_pence(entry: CaseTimeEntry, user: User | None) -> int | None:
    if entry.non_billable:
        return None
    rate = user.charge_rate_pence_per_hour if user else None
    return time_entry_value_pence(entry.duration_minutes, rate)


def billing_vat_rate_bps(db: Session) -> int:
    settings = get_billing_settings(db)
    return round(float(settings.default_vat_percent) * 100)


def format_time_invoice_description(entry: CaseTimeEntry) -> str:
    tenths = entry.duration_minutes // TIME_UNIT_MINUTES
    hrs = tenths / 10
    hrs_label = f"{hrs:g}" if hrs == int(hrs) else f"{hrs:.1f}"
    desc = f"{entry.work_date.isoformat()} — {entry.description.strip()} ({hrs_label} hr)"
    if len(desc) > 500:
        return desc[:497] + "..."
    return desc


def time_invoice_line_spec(entry: CaseTimeEntry, db: Session, vat_rate_bps: int) -> CaseInvoiceLineCreate:
    if entry.non_billable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Non-billable time entries cannot be added to an invoice.",
        )
    user = db.get(User, entry.user_id)
    rate = user.charge_rate_pence_per_hour if user else None
    amount = time_entry_value_pence(entry.duration_minutes, rate)
    if not amount or amount <= 0:
        name = (user.display_name or user.email or "user").strip() if user else "user"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot bill time for {name}: charge rate is not set.",
        )
    tax = round(amount * vat_rate_bps / 10000)
    return CaseInvoiceLineCreate(
        line_type="fee",
        description=format_time_invoice_description(entry),
        amount_pence=amount,
        tax_pence=tax,
        credit_user_id=entry.user_id,
    )


@dataclass
class TimeEntryLinePair:
    entry: CaseTimeEntry
    spec: CaseInvoiceLineCreate


def resolve_unbilled_time_entries_for_billing(
    case_id: uuid.UUID,
    time_entry_ids: list[uuid.UUID],
    db: Session,
) -> list[TimeEntryLinePair]:
    if not time_entry_ids:
        return []
    uniq = list(dict.fromkeys(time_entry_ids))
    vat_bps = billing_vat_rate_bps(db)
    pairs: list[TimeEntryLinePair] = []
    for eid in uniq:
        entry = db.get(CaseTimeEntry, eid)
        if not entry or entry.case_id != case_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Time entry {eid} not found on this matter.",
            )
        if entry.status != CaseTimeEntryStatus.unbilled:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only unbilled time entries can be added to an invoice.",
            )
        if entry.non_billable:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Non-billable time entries cannot be added to an invoice.",
            )
        pairs.append(TimeEntryLinePair(entry=entry, spec=time_invoice_line_spec(entry, db, vat_bps)))
    return pairs


def mark_time_entries_billed(
    db: Session,
    pairs: list[tuple[CaseTimeEntry, CaseInvoiceLine]],
) -> None:
    now = datetime.utcnow()
    for entry, ln in pairs:
        entry.status = CaseTimeEntryStatus.billed
        entry.invoice_line_id = ln.id
        entry.updated_at = now
        db.add(entry)


def release_billed_time_entries_for_invoice(invoice_id: uuid.UUID, db: Session) -> None:
    line_ids = (
        db.execute(select(CaseInvoiceLine.id).where(CaseInvoiceLine.invoice_id == invoice_id))
        .scalars()
        .all()
    )
    if not line_ids:
        return
    rows = (
        db.execute(select(CaseTimeEntry).where(CaseTimeEntry.invoice_line_id.in_(line_ids)))
        .scalars()
        .all()
    )
    now = datetime.utcnow()
    for entry in rows:
        entry.status = CaseTimeEntryStatus.unbilled
        entry.invoice_line_id = None
        entry.updated_at = now
        db.add(entry)


def wip_age_bucket(age_days: int) -> str:
    if age_days <= 30:
        return "0-30"
    if age_days <= 90:
        return "31-90"
    return "90+"


def user_may_modify_time_entry(entry: CaseTimeEntry, actor: User, db: Session) -> bool:
    if entry.created_by_user_id == actor.id or entry.user_id == actor.id:
        return True
    return user_effective_admin(actor, db)


def assert_entry_editable(entry: CaseTimeEntry) -> None:
    if entry.status != CaseTimeEntryStatus.unbilled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only unbilled time entries can be changed.",
        )


def resolve_time_entry_user_id(
    *,
    payload_user_id: uuid.UUID | None,
    actor: User,
    db: Session,
) -> uuid.UUID:
    if payload_user_id is None or payload_user_id == actor.id:
        return actor.id
    if not user_effective_admin(actor, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can log time for another user.",
        )
    target = db.get(User, payload_user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="User not found.")
    return target.id


def time_entry_out(entry: CaseTimeEntry, db: Session) -> dict:
    user = db.get(User, entry.user_id)
    rate = user.charge_rate_pence_per_hour if user else None
    return {
        "id": entry.id,
        "case_id": entry.case_id,
        "user_id": entry.user_id,
        "user_display_name": (user.display_name or user.email or "").strip() if user else "",
        "created_by_user_id": entry.created_by_user_id,
        "work_date": entry.work_date,
        "duration_minutes": entry.duration_minutes,
        "duration_tenths": entry.duration_minutes // TIME_UNIT_MINUTES,
        "description": entry.description,
        "status": entry.status.value,
        "invoice_line_id": entry.invoice_line_id,
        "non_billable": entry.non_billable,
        "charge_rate_pence_per_hour": rate,
        "value_pence": entry_billable_value_pence(entry, user),
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


@dataclass
class WipReportFeeEarnerRow:
    user_id: uuid.UUID
    display_name: str
    duration_minutes: int
    value_pence: int
    entry_count: int


@dataclass
class WipReportEntryRow:
    entry_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    user_id: uuid.UUID
    fee_earner_name: str
    work_date: date
    duration_minutes: int
    description: str
    value_pence: int | None
    age_days: int
    age_bucket: str


def report_wip(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    as_of: date | None = None,
) -> tuple[list[WipReportFeeEarnerRow], list[WipReportEntryRow], dict[str, int]]:
    today = as_of or datetime.now(timezone.utc).date()
    q = (
        select(CaseTimeEntry, Case)
        .join(Case, Case.id == CaseTimeEntry.case_id)
        .where(
            CaseTimeEntry.status == CaseTimeEntryStatus.unbilled,
            CaseTimeEntry.non_billable.is_(False),
            CaseTimeEntry.user_id.in_(fee_earner_user_ids),
        )
        .order_by(CaseTimeEntry.work_date.asc(), Case.case_number.asc())
    )
    pairs = db.execute(q).all()
    by_user: dict[uuid.UUID, WipReportFeeEarnerRow] = {}
    entries: list[WipReportEntryRow] = []
    tot_minutes = 0
    tot_value = 0
    tot_count = 0
    for entry, case in pairs:
        user = db.get(User, entry.user_id)
        name = (user.display_name or user.email or "").strip() if user else ""
        value = entry_billable_value_pence(entry, user)
        age_days = max(0, (today - entry.work_date).days)
        bucket = wip_age_bucket(age_days)
        entries.append(
            WipReportEntryRow(
                entry_id=entry.id,
                case_id=case.id,
                case_number=case.case_number,
                client_name=case.client_name,
                user_id=entry.user_id,
                fee_earner_name=name,
                work_date=entry.work_date,
                duration_minutes=entry.duration_minutes,
                description=entry.description,
                value_pence=value,
                age_days=age_days,
                age_bucket=bucket,
            )
        )
        tot_minutes += entry.duration_minutes
        tot_count += 1
        if value is not None:
            tot_value += value
        agg = by_user.get(entry.user_id)
        if agg is None:
            by_user[entry.user_id] = WipReportFeeEarnerRow(
                user_id=entry.user_id,
                display_name=name,
                duration_minutes=entry.duration_minutes,
                value_pence=value or 0,
                entry_count=1,
            )
        else:
            agg.duration_minutes += entry.duration_minutes
            agg.value_pence += value or 0
            agg.entry_count += 1
    summary = sorted(by_user.values(), key=lambda r: r.display_name.lower())
    totals = {
        "duration_minutes": tot_minutes,
        "value_pence": tot_value,
        "entry_count": tot_count,
    }
    return summary, entries, totals


@dataclass
class TimeRecordedFeeEarnerRow:
    user_id: uuid.UUID
    display_name: str
    duration_minutes: int
    billable_minutes: int
    nil_rate_minutes: int
    value_pence: int
    entry_count: int
    unbilled_minutes: int
    billed_minutes: int
    written_off_minutes: int


@dataclass
class TimeRecordedEntryRow:
    entry_id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    user_id: uuid.UUID
    fee_earner_name: str
    work_date: date
    duration_minutes: int
    description: str
    non_billable: bool
    status: str
    value_pence: int | None


def report_time_recorded(
    fee_earner_user_ids: list[uuid.UUID],
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[TimeRecordedFeeEarnerRow], list[TimeRecordedEntryRow], dict[str, int]]:
    q = (
        select(CaseTimeEntry, Case)
        .join(Case, Case.id == CaseTimeEntry.case_id)
        .where(CaseTimeEntry.user_id.in_(fee_earner_user_ids))
        .order_by(CaseTimeEntry.work_date.asc(), Case.case_number.asc(), CaseTimeEntry.created_at.asc())
    )
    if date_from is not None:
        q = q.where(CaseTimeEntry.work_date >= date_from)
    if date_to is not None:
        q = q.where(CaseTimeEntry.work_date <= date_to)
    pairs = db.execute(q).all()
    by_user: dict[uuid.UUID, TimeRecordedFeeEarnerRow] = {}
    entries: list[TimeRecordedEntryRow] = []
    tot_minutes = 0
    tot_billable_minutes = 0
    tot_nil_minutes = 0
    tot_value = 0
    tot_count = 0
    tot_unbilled = 0
    tot_billed = 0
    tot_written_off = 0
    for entry, case in pairs:
        user = db.get(User, entry.user_id)
        name = (user.display_name or user.email or "").strip() if user else ""
        value = entry_billable_value_pence(entry, user)
        status = entry.status.value
        entries.append(
            TimeRecordedEntryRow(
                entry_id=entry.id,
                case_id=case.id,
                case_number=case.case_number,
                client_name=case.client_name,
                user_id=entry.user_id,
                fee_earner_name=name,
                work_date=entry.work_date,
                duration_minutes=entry.duration_minutes,
                description=entry.description,
                non_billable=entry.non_billable,
                status=status,
                value_pence=value,
            )
        )
        mins = entry.duration_minutes
        tot_minutes += mins
        tot_count += 1
        if entry.non_billable:
            tot_nil_minutes += mins
        else:
            tot_billable_minutes += mins
            if value is not None:
                tot_value += value
        if status == CaseTimeEntryStatus.unbilled.value:
            tot_unbilled += mins
        elif status == CaseTimeEntryStatus.billed.value:
            tot_billed += mins
        else:
            tot_written_off += mins
        agg = by_user.get(entry.user_id)
        if agg is None:
            by_user[entry.user_id] = TimeRecordedFeeEarnerRow(
                user_id=entry.user_id,
                display_name=name,
                duration_minutes=mins,
                billable_minutes=0 if entry.non_billable else mins,
                nil_rate_minutes=mins if entry.non_billable else 0,
                value_pence=value or 0,
                entry_count=1,
                unbilled_minutes=mins if status == CaseTimeEntryStatus.unbilled.value else 0,
                billed_minutes=mins if status == CaseTimeEntryStatus.billed.value else 0,
                written_off_minutes=mins if status == CaseTimeEntryStatus.written_off.value else 0,
            )
        else:
            agg.duration_minutes += mins
            if entry.non_billable:
                agg.nil_rate_minutes += mins
            else:
                agg.billable_minutes += mins
                agg.value_pence += value or 0
            agg.entry_count += 1
            if status == CaseTimeEntryStatus.unbilled.value:
                agg.unbilled_minutes += mins
            elif status == CaseTimeEntryStatus.billed.value:
                agg.billed_minutes += mins
            else:
                agg.written_off_minutes += mins
    summary = sorted(by_user.values(), key=lambda r: r.display_name.lower())
    totals = {
        "duration_minutes": tot_minutes,
        "billable_minutes": tot_billable_minutes,
        "nil_rate_minutes": tot_nil_minutes,
        "value_pence": tot_value,
        "entry_count": tot_count,
        "unbilled_minutes": tot_unbilled,
        "billed_minutes": tot_billed,
        "written_off_minutes": tot_written_off,
    }
    return summary, entries, totals

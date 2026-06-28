"""Sub-menu Events: admin templates per matter sub-type + case-level dated rows."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import map_cases_if_accessible
from app.models import (
    CalendarEventEmailAlertSubscription,
    Case,
    CaseEvent,
    MatterSubType,
    MatterSubTypeEventTemplate,
    User,
)
from app.schemas import (
    CalendarEventTemplatePickOut,
    CaseEventCreate,
    CaseEventOut,
    CaseEventsOut,
    CaseEventUpdate,
    MatterSubTypeEventTemplateCreate,
    MatterSubTypeEventTemplateOut,
    MatterSubTypeEventTemplateUpdate,
)

UK = ZoneInfo("Europe/London")


def _require_sub_type(sub_type_id: uuid.UUID, db: Session) -> MatterSubType:
    sub = db.get(MatterSubType, sub_type_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter sub type not found")
    return sub


def list_calendar_event_template_picks(db: Session) -> list[CalendarEventTemplatePickOut]:
    """All admin-defined event line templates, grouped for the main calendar UI via ``matter_sub_type_name``."""
    rows = (
        db.execute(
            select(MatterSubTypeEventTemplate, MatterSubType.name)
            .join(MatterSubType, MatterSubType.id == MatterSubTypeEventTemplate.matter_sub_type_id)
            .order_by(
                MatterSubType.name.asc(),
                MatterSubTypeEventTemplate.sort_order.asc(),
                MatterSubTypeEventTemplate.created_at.asc(),
            )
        )
        .all()
    )
    out: list[CalendarEventTemplatePickOut] = []
    for row in rows:
        t = row[0]
        st_name = row[1]
        out.append(
            CalendarEventTemplatePickOut(
                id=t.id,
                matter_sub_type_id=t.matter_sub_type_id,
                matter_sub_type_name=st_name,
                name=t.name,
                sort_order=t.sort_order,
                notify_on_day=bool(t.notify_on_day),
                notify_every_n=t.notify_every_n,
                notify_every_unit=t.notify_every_unit
                if t.notify_every_unit in ("days", "weeks", "months")
                else None,
            )
        )
    return out


def list_event_templates(sub_type_id: uuid.UUID, db: Session) -> list[MatterSubTypeEventTemplateOut]:
    _require_sub_type(sub_type_id, db)
    rows = (
        db.execute(
            select(MatterSubTypeEventTemplate)
            .where(MatterSubTypeEventTemplate.matter_sub_type_id == sub_type_id)
            .order_by(MatterSubTypeEventTemplate.sort_order, MatterSubTypeEventTemplate.created_at)
        )
        .scalars()
        .all()
    )
    return [MatterSubTypeEventTemplateOut.model_validate(r, from_attributes=True) for r in rows]


def create_event_template(
    payload: MatterSubTypeEventTemplateCreate, db: Session
) -> MatterSubTypeEventTemplateOut:
    _require_sub_type(payload.matter_sub_type_id, db)
    now = datetime.utcnow()
    row = MatterSubTypeEventTemplate(
        id=uuid.uuid4(),
        matter_sub_type_id=payload.matter_sub_type_id,
        name=payload.name.strip(),
        sort_order=payload.sort_order,
        notify_on_day=payload.notify_on_day,
        notify_every_n=payload.notify_every_n,
        notify_every_unit=payload.notify_every_unit,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return MatterSubTypeEventTemplateOut.model_validate(row, from_attributes=True)


def update_event_template(
    template_id: uuid.UUID, payload: MatterSubTypeEventTemplateUpdate, db: Session
) -> MatterSubTypeEventTemplateOut:
    row = db.get(MatterSubTypeEventTemplate, template_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event template not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        row.name = data["name"].strip()
    if "sort_order" in data and data["sort_order"] is not None:
        row.sort_order = data["sort_order"]
    if "notify_on_day" in data and data["notify_on_day"] is not None:
        row.notify_on_day = bool(data["notify_on_day"])
    if "notify_every_n" in data:
        row.notify_every_n = data["notify_every_n"]
    if "notify_every_unit" in data:
        row.notify_every_unit = data["notify_every_unit"]
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.flush()
    return MatterSubTypeEventTemplateOut.model_validate(row, from_attributes=True)


def delete_event_template(template_id: uuid.UUID, db: Session) -> None:
    row = db.get(MatterSubTypeEventTemplate, template_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event template not found")
    db.delete(row)
    db.flush()


def _calendar_block_for_event(e: CaseEvent) -> tuple[str | None, str | None, bool | None]:
    """ISO UTC (Z) timed range, or YYYY-MM-DD all-day pair matching CalDAV create body."""
    if e.event_date is None:
        return None, None, None
    if e.event_all_day:
        start = e.event_date.isoformat()
        end = (e.event_date + timedelta(days=1)).isoformat()
        return start, end, True
    ev_time = e.event_start_time or time(9, 0)
    dt0 = datetime.combine(e.event_date, ev_time, tzinfo=UK)
    dt1 = dt0 + timedelta(hours=1)
    z = timezone.utc
    s = dt0.astimezone(z).strftime("%Y-%m-%dT%H:%M:%SZ")
    en = dt1.astimezone(z).strftime("%Y-%m-%dT%H:%M:%SZ")
    return s, en, False


def _event_out(e: CaseEvent, *, email_alert_enabled: bool = False) -> CaseEventOut:
    cs, ce, cad = _calendar_block_for_event(e)
    return CaseEventOut(
        id=e.id,
        case_id=e.case_id,
        template_id=e.template_id,
        name=e.name,
        sort_order=e.sort_order,
        event_date=e.event_date,
        event_all_day=e.event_all_day,
        event_start_time=e.event_start_time,
        calendar_block_start=cs,
        calendar_block_end=ce,
        calendar_block_all_day=cad,
        track_in_calendar=e.track_in_calendar,
        calendar_event_uid=e.calendar_event_uid,
        email_alert_enabled=email_alert_enabled,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


def _get_or_init_case_events(case_id: uuid.UUID, db: Session) -> list[CaseEvent]:
    existing = (
        db.execute(
            select(CaseEvent)
            .where(CaseEvent.case_id == case_id)
            .order_by(CaseEvent.sort_order, CaseEvent.created_at)
        )
        .scalars()
        .all()
    )
    if existing:
        return list(existing)

    case = db.get(Case, case_id)
    if not case or not case.matter_sub_type_id:
        return []

    templates = (
        db.execute(
            select(MatterSubTypeEventTemplate)
            .where(MatterSubTypeEventTemplate.matter_sub_type_id == case.matter_sub_type_id)
            .order_by(MatterSubTypeEventTemplate.sort_order, MatterSubTypeEventTemplate.created_at)
        )
        .scalars()
        .all()
    )
    if not templates:
        return []

    now = datetime.utcnow()
    out: list[CaseEvent] = []
    for t in templates:
        ce = CaseEvent(
            id=uuid.uuid4(),
            case_id=case_id,
            template_id=t.id,
            name=t.name,
            sort_order=t.sort_order,
            event_date=None,
            event_all_day=True,
            event_start_time=None,
            created_at=now,
            updated_at=now,
        )
        db.add(ce)
        out.append(ce)
    db.flush()
    return out


def get_case_events(case_id: uuid.UUID, db: Session, *, viewer: User) -> CaseEventsOut:
    from app.calendar_email_alert_service import case_event_key

    rows = _get_or_init_case_events(case_id, db)
    if not rows:
        return CaseEventsOut(case_id=case_id, events=[])
    keys = [case_event_key(e.id) for e in rows]
    enabled_keys = set(
        db.execute(
            select(CalendarEventEmailAlertSubscription.event_key).where(
                CalendarEventEmailAlertSubscription.user_id == viewer.id,
                CalendarEventEmailAlertSubscription.enabled.is_(True),
                CalendarEventEmailAlertSubscription.event_key.in_(keys),
            )
        )
        .scalars()
        .all()
    )
    out_events: list[CaseEventOut] = []
    for e in rows:
        ek = case_event_key(e.id)
        out_events.append(_event_out(e, email_alert_enabled=ek in enabled_keys))
    return CaseEventsOut(case_id=case_id, events=out_events)


def create_custom_case_event(
    case_id: uuid.UUID,
    payload: CaseEventCreate,
    db: Session,
    *,
    actor_user_id: uuid.UUID,
) -> CaseEventOut:
    """Add a case-specific event line (no admin template) with optional schedule + tracking."""
    from app.event_tracked_tasks import sync_tracked_case_event_task

    _get_or_init_case_events(case_id, db)
    mx = db.execute(select(func.max(CaseEvent.sort_order)).where(CaseEvent.case_id == case_id)).scalar()
    next_order = (int(mx) + 1) if mx is not None else 0
    now = datetime.utcnow()
    all_day = payload.event_all_day
    start_t = payload.event_start_time
    if not all_day and payload.event_date is not None and start_t is None:
        start_t = time(9, 0)
    ce = CaseEvent(
        id=uuid.uuid4(),
        case_id=case_id,
        template_id=None,
        name=payload.name.strip(),
        sort_order=next_order,
        event_date=payload.event_date,
        event_all_day=all_day,
        event_start_time=None if all_day else start_t,
        track_in_calendar=payload.track_in_calendar,
        created_at=now,
        updated_at=now,
    )
    db.add(ce)
    db.flush()
    case = db.get(Case, case_id)
    if case:
        sync_tracked_case_event_task(db, case=case, case_event=ce, actor_user_id=actor_user_id)
    db.flush()
    from app.calendar_email_alert_service import case_event_key, sync_case_event_subscription, user_has_email_alert

    sync_case_event_subscription(db, viewer_id=actor_user_id, case_event=ce, email_alert=payload.email_alert)
    return _event_out(ce, email_alert_enabled=user_has_email_alert(db, actor_user_id, case_event_key(ce.id)))


def update_case_event(
    case_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: CaseEventUpdate,
    db: Session,
    *,
    actor_user_id: uuid.UUID,
) -> CaseEventOut:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update.",
        )
    _get_or_init_case_events(case_id, db)
    e = db.get(CaseEvent, event_id)
    if not e or e.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case event not found")
    if "name" in data and data["name"] is not None:
        e.name = str(data["name"]).strip()
    if "event_date" in data:
        e.event_date = data["event_date"]
    if "event_all_day" in data and data["event_all_day"] is not None:
        e.event_all_day = bool(data["event_all_day"])
    if "event_start_time" in data:
        e.event_start_time = data["event_start_time"]
    if "track_in_calendar" in data:
        e.track_in_calendar = bool(data["track_in_calendar"])
    if "calendar_event_uid" in data:
        e.calendar_event_uid = data["calendar_event_uid"]
    if e.event_all_day:
        e.event_start_time = None
    elif e.event_date is not None and e.event_start_time is None:
        e.event_start_time = time(9, 0)
    e.updated_at = datetime.utcnow()
    db.add(e)
    db.flush()

    from app.event_tracked_tasks import sync_tracked_case_event_task

    case = db.get(Case, case_id)
    if case:
        sync_tracked_case_event_task(db, case=case, case_event=e, actor_user_id=actor_user_id)
    db.flush()

    from app.calendar_email_alert_service import case_event_key, refresh_case_event_subscription_snapshot, sync_case_event_subscription, user_has_email_alert

    if "email_alert" in data:
        sync_case_event_subscription(db, viewer_id=actor_user_id, case_event=e, email_alert=data["email_alert"])
    refresh_case_event_subscription_snapshot(db, viewer_id=actor_user_id, case_event=e)
    return _event_out(e, email_alert_enabled=user_has_email_alert(db, actor_user_id, case_event_key(e.id)))


def _case_event_intersects_window(ce: CaseEvent, rs: datetime, re: datetime) -> bool:
    """Whether the CaseEvent's scheduled block overlaps ``[rs, re)`` (UTC-aware datetimes)."""
    if ce.event_date is None:
        return False
    z = timezone.utc
    rs_u = rs if rs.tzinfo else rs.replace(tzinfo=z)
    re_u = re if re.tzinfo else re.replace(tzinfo=z)
    cs, ce_str, cad = _calendar_block_for_event(ce)
    if not cs or not ce_str:
        return False
    if cad:
        d = ce.event_date
        ds = datetime(d.year, d.month, d.day, tzinfo=z)
        de = ds + timedelta(days=1)
        return de > rs_u and ds < re_u
    s = datetime.fromisoformat(cs.replace("Z", "+00:00"))
    e = datetime.fromisoformat(ce_str.replace("Z", "+00:00"))
    return e > rs_u and s < re_u


def list_tracked_case_events_for_calendar_merge(
    db: Session,
    user: User,
    range_start: datetime,
    range_end: datetime,
) -> list[dict]:
    """Pseudo-calendar rows for matter events with ``track_in_calendar`` and a date (main calendar feed)."""
    z = timezone.utc
    rs_u = range_start if range_start.tzinfo else range_start.replace(tzinfo=z)
    re_u = range_end if range_end.tzinfo else range_end.replace(tzinfo=z)

    start_d = rs_u.date()
    end_d = re_u.date()
    if end_d < start_d:
        return []

    rows = (
        db.execute(
            select(CaseEvent).where(
                CaseEvent.track_in_calendar.is_(True),
                CaseEvent.event_date.isnot(None),
                CaseEvent.calendar_event_uid.is_(None),
                CaseEvent.event_date >= start_d,
                CaseEvent.event_date <= end_d,
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []

    cases = map_cases_if_accessible(db, user, {ev.case_id for ev in rows})
    out: list[dict] = []
    for ev in rows:
        case = cases.get(ev.case_id)
        if case is None:
            continue
        if not _case_event_intersects_window(ev, rs_u, re_u):
            continue
        cs, ce_str, cad = _calendar_block_for_event(ev)
        if not cs or not ce_str:
            continue
        syn_id = f"caseevt-{ev.id}"
        title = f"{case.case_number} · {ev.name}"
        out.append(
            {
                "id": syn_id,
                "uid": syn_id,
                "title": title,
                "start": cs,
                "end": ce_str,
                "all_day": bool(cad),
                "description": None,
                "calendar_name": None,
                "calendar_id": None,
                "can_edit": True,
                "category_id": None,
                "category_name": None,
                "category_color": None,
                "case_id": case.id,
                "case_event_id": ev.id,
                "track_in_calendar": ev.track_in_calendar,
                "matter_template_id": str(ev.template_id) if ev.template_id else None,
            }
        )
    return out


def enrich_caldav_events_with_linked_case_events(
    db: Session,
    user: User,
    events: list[dict],
) -> None:
    """Attach matter metadata to CalDAV rows synced from tracked case events."""
    refs = {str(item.get("id") or "").strip() for item in events if not item.get("case_event_id")}
    refs.discard("")
    if not refs:
        return

    rows = (
        db.execute(
            select(CaseEvent).where(
                CaseEvent.track_in_calendar.is_(True),
                CaseEvent.calendar_event_uid.in_(refs),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return

    cases = map_cases_if_accessible(db, user, {ev.case_id for ev in rows})
    by_ref: dict[str, CaseEvent] = {}
    for ev in rows:
        ref = (ev.calendar_event_uid or "").strip()
        if not ref or ev.case_id not in cases:
            continue
        by_ref[ref] = ev

    for item in events:
        if item.get("case_event_id"):
            continue
        ref = str(item.get("id") or "")
        ev = by_ref.get(ref)
        if ev is None:
            continue
        case = cases[ev.case_id]
        item["case_id"] = str(case.id)
        item["case_event_id"] = str(ev.id)
        item["track_in_calendar"] = ev.track_in_calendar
        item["title"] = f"{case.case_number} · {ev.name}"
        if ev.template_id:
            item["matter_template_id"] = str(ev.template_id)

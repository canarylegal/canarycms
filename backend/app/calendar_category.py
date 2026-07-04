"""Calendar categories (Canary DB + CalDAV CATEGORIES name sync)."""
from __future__ import annotations

import os
import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from app.models import CalendarEventCategory, UserCalendarCategory


def normalize_calendar_color(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if s.startswith("#"):
        s = s[1:]
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", s):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Color must be empty or #RRGGBB (6 hex digits)",
        )
    return f"#{s.upper()}"


def require_category_on_calendar(db: Session, calendar_id: uuid.UUID, category_id: uuid.UUID) -> UserCalendarCategory:
    cat = db.get(UserCalendarCategory, category_id)
    if not cat or cat.calendar_id != calendar_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found on this calendar")
    return cat


def set_event_category_link(
    db: Session,
    calendar_id: uuid.UUID,
    event_uid: str,
    category_id: uuid.UUID | None,
) -> None:
    db.execute(
        delete(CalendarEventCategory).where(
            CalendarEventCategory.calendar_id == calendar_id,
            CalendarEventCategory.event_uid == event_uid,
        )
    )
    if category_id is not None:
        require_category_on_calendar(db, calendar_id, category_id)
        db.add(
            CalendarEventCategory(
                calendar_id=calendar_id,
                event_uid=event_uid,
                category_id=category_id,
            )
        )


def delete_event_category_link(db: Session, calendar_id: uuid.UUID, event_uid: str) -> None:
    db.execute(
        delete(CalendarEventCategory).where(
            CalendarEventCategory.calendar_id == calendar_id,
            CalendarEventCategory.event_uid == event_uid,
        )
    )


def _caldav_category_sync_enabled() -> bool:
    return (os.getenv("CANARY_SYNC_CALDAV_EVENT_CATEGORIES") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _category_id_for_caldav_names(
    db: Session,
    calendar_id: uuid.UUID,
    names: list[str],
    *,
    categories_by_calendar: dict[uuid.UUID, dict[str, uuid.UUID]] | None = None,
) -> uuid.UUID | None:
    if not names:
        return None
    if categories_by_calendar is not None:
        by_name = categories_by_calendar.get(calendar_id, {})
    else:
        rows = db.execute(
            select(UserCalendarCategory.id, UserCalendarCategory.name).where(
                UserCalendarCategory.calendar_id == calendar_id
            )
        ).all()
        by_name = {row.name: row.id for row in rows}
        by_name.update({row.name.lower(): row.id for row in rows})
    for name in names:
        n = (name or "").strip()
        if not n:
            continue
        if n in by_name:
            return by_name[n]
        lower = by_name.get(n.lower())
        if lower is not None:
            return lower
    return None


def reconcile_event_categories_from_caldav(
    db: Session,
    items: list[dict],
    *,
    writable_calendar_ids: set[uuid.UUID],
) -> int:
    """Import CalDAV CATEGORIES names into Canary event category links (Outlook → Canary).

    When an event has no CATEGORIES, any Canary link is cleared. Unknown category names are
    left unchanged so legacy Outlook labels do not wipe Canary assignments.
    """
    if not _caldav_category_sync_enabled() or not writable_calendar_ids or not items:
        return 0

    pairs: list[tuple[uuid.UUID, str]] = []
    for it in items:
        cid_raw = it.get("calendar_id")
        uid = it.get("uid")
        if not cid_raw or not uid:
            continue
        try:
            cid = uuid.UUID(str(cid_raw))
        except ValueError:
            continue
        if cid not in writable_calendar_ids:
            continue
        pairs.append((cid, str(uid)))
    if not pairs:
        return 0

    uniq = list(dict.fromkeys(pairs))
    existing: dict[tuple[uuid.UUID, str], uuid.UUID | None] = {}
    for link, cat in db.execute(
        select(CalendarEventCategory, UserCalendarCategory)
        .outerjoin(UserCalendarCategory, UserCalendarCategory.id == CalendarEventCategory.category_id)
        .where(tuple_(CalendarEventCategory.calendar_id, CalendarEventCategory.event_uid).in_(uniq))
    ).all():
        existing[(link.calendar_id, link.event_uid)] = cat.id if cat is not None else None

    cal_ids = {cid for cid, _ in uniq}
    categories_by_calendar: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
    for cal_id in cal_ids:
        rows = db.execute(
            select(UserCalendarCategory.id, UserCalendarCategory.name).where(
                UserCalendarCategory.calendar_id == cal_id
            )
        ).all()
        name_map: dict[str, uuid.UUID] = {}
        for row in rows:
            name_map[row.name] = row.id
            name_map[row.name.lower()] = row.id
        categories_by_calendar[cal_id] = name_map

    changes = 0
    for it in items:
        cid_raw = it.get("calendar_id")
        uid = it.get("uid")
        if not cid_raw or not uid:
            continue
        try:
            cid = uuid.UUID(str(cid_raw))
        except ValueError:
            continue
        if cid not in writable_calendar_ids:
            continue
        names = it.get("caldav_category_names")
        if names is None:
            continue
        key = (cid, str(uid))
        current = existing.get(key)
        if names:
            target = _category_id_for_caldav_names(
                db, cid, names, categories_by_calendar=categories_by_calendar
            )
            if target is None:
                continue
        else:
            target = None
        if current == target:
            continue
        set_event_category_link(db, cid, str(uid), target)
        existing[key] = target
        changes += 1
    return changes


def enrich_events_with_categories(db: Session, items: list[dict]) -> None:
    pairs: list[tuple[uuid.UUID, str]] = []
    for it in items:
        cid = it.get("calendar_id")
        uid = it.get("uid")
        if not cid or not uid:
            continue
        try:
            pairs.append((uuid.UUID(str(cid)), str(uid)))
        except ValueError:
            continue
    if not pairs:
        return
    uniq = list(dict.fromkeys(pairs))
    stmt = (
        select(CalendarEventCategory, UserCalendarCategory)
        .outerjoin(UserCalendarCategory, UserCalendarCategory.id == CalendarEventCategory.category_id)
        .where(tuple_(CalendarEventCategory.calendar_id, CalendarEventCategory.event_uid).in_(uniq))
    )
    by_key: dict[tuple[uuid.UUID, str], UserCalendarCategory | None] = {}
    for link, cat in db.execute(stmt).all():
        by_key[(link.calendar_id, link.event_uid)] = cat

    for it in items:
        cid = it.get("calendar_id")
        uid = it.get("uid")
        if not cid or not uid:
            continue
        try:
            key = (uuid.UUID(str(cid)), str(uid))
        except ValueError:
            continue
        cat = by_key.get(key)
        if cat is None:
            it["category_id"] = None
            it["category_name"] = None
            it["category_color"] = None
            continue
        it["category_id"] = str(cat.id)
        it["category_name"] = cat.name
        it["category_color"] = cat.color


def enrich_events_with_default_colors(db: Session, items: list[dict]) -> None:
    """Apply per-calendar default_event_color when an event has no category link."""
    from app.models import UserCalendar

    calendar_ids: set[uuid.UUID] = set()
    for it in items:
        if it.get("category_color"):
            continue
        cid = it.get("calendar_id")
        if not cid:
            continue
        try:
            calendar_ids.add(uuid.UUID(str(cid)))
        except ValueError:
            continue
    if not calendar_ids:
        return
    rows = db.execute(
        select(UserCalendar.id, UserCalendar.default_event_color).where(
            UserCalendar.id.in_(calendar_ids),
            UserCalendar.default_event_color.isnot(None),
        )
    ).all()
    by_id = {row.id: row.default_event_color for row in rows if row.default_event_color}
    if not by_id:
        return
    for it in items:
        if it.get("category_color"):
            continue
        try:
            cid = uuid.UUID(str(it.get("calendar_id")))
        except (ValueError, TypeError):
            continue
        color = by_id.get(cid)
        if color:
            it["category_color"] = color

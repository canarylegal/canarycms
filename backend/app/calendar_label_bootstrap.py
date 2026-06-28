"""Optional firm calendar labels (Canary UI + CalDAV CATEGORIES sync)."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalendarEventCategory, User, UserCalendar, UserCalendarCategory
from app.radicale_calendar import event_href_by_uid, update_event_on_principal

log = logging.getLogger(__name__)

_CATEGORY_NAME_UNSET = object()


@dataclass(frozen=True)
class CalendarLabelSpec:
    name: str
    color: str | None


def _normalize_bootstrap_color(raw: object | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6 or not all(c in "0123456789ABCDEFabcdef" for c in s):
        log.warning("Ignoring invalid calendar label color %r", raw)
        return None
    return f"#{s.upper()}"


def parse_calendar_label_specs() -> list[CalendarLabelSpec]:
    """Read ``CANARY_CALENDAR_LABEL_SPECS`` JSON array of ``{name, color?}`` objects."""
    raw = (os.getenv("CANARY_CALENDAR_LABEL_SPECS") or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("CANARY_CALENDAR_LABEL_SPECS is not valid JSON: %s", e)
        return []
    if not isinstance(payload, list):
        log.warning("CANARY_CALENDAR_LABEL_SPECS must be a JSON array")
        return []
    out: list[CalendarLabelSpec] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        color_raw = item.get("color")
        color = _normalize_bootstrap_color(color_raw)
        out.append(CalendarLabelSpec(name=name[:120], color=color))
    return out


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def ensure_calendar_labels(db: Session, calendar_id: uuid.UUID) -> bool:
    """Insert missing label rows for one calendar. Returns True if any row was added."""
    specs = parse_calendar_label_specs()
    if not specs:
        return False
    changed = False
    for spec in specs:
        existing = (
            db.execute(
                select(UserCalendarCategory.id).where(
                    UserCalendarCategory.calendar_id == calendar_id,
                    UserCalendarCategory.name == spec.name,
                )
            )
            .scalar_one_or_none()
        )
        if existing is not None:
            continue
        db.add(
            UserCalendarCategory(
                calendar_id=calendar_id,
                name=spec.name,
                color=spec.color,
            )
        )
        changed = True
    return changed


def sync_caldav_categories_for_calendar(db: Session, calendar: UserCalendar) -> int:
    """Write CATEGORIES on CalDAV events that have a Canary label link. Returns update count."""
    if not _truthy(os.getenv("CANARY_SYNC_CALDAV_EVENT_CATEGORIES", "1")):
        return 0
    owner = db.get(User, calendar.owner_user_id)
    if owner is None or not owner.caldav_password_enc:
        return 0
    rows = db.execute(
        select(CalendarEventCategory, UserCalendarCategory)
        .outerjoin(UserCalendarCategory, UserCalendarCategory.id == CalendarEventCategory.category_id)
        .where(CalendarEventCategory.calendar_id == calendar.id)
    ).all()
    updated = 0
    for link, cat in rows:
        href = event_href_by_uid(owner, calendar.radicale_slug, link.event_uid)
        if not href:
            continue
        name = cat.name if cat is not None else None
        try:
            update_event_on_principal(
                owner,
                href,
                calendar_display_name=calendar.name,
                calendar_id=str(calendar.id),
                category_name=name,
            )
            updated += 1
        except Exception as e:
            log.debug(
                "CalDAV category sync skipped calendar=%s uid=%s: %s",
                calendar.id,
                link.event_uid,
                e,
            )
    return updated


def ensure_calendar_labels_all_calendars(db: Session) -> None:
    """Apply firm label specs to every user calendar; optionally sync CATEGORIES to Radicale."""
    if not parse_calendar_label_specs():
        return
    calendars = db.execute(select(UserCalendar)).scalars().all()
    labels_added = 0
    events_synced = 0
    for cal in calendars:
        if ensure_calendar_labels(db, cal.id):
            labels_added += 1
        events_synced += sync_caldav_categories_for_calendar(db, cal)
    if labels_added or events_synced:
        db.commit()
        log.info(
            "Calendar label bootstrap: %d calendar(s) gained labels, %d CalDAV event(s) synced",
            labels_added,
            events_synced,
        )

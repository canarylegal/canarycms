"""Calendar e-mail alert subscriptions + scheduled sends."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    CalendarEventEmailAlertSubscription,
    CalendarEventNotificationSent,
    CaseEvent,
    NotificationOutbox,
    MatterSubTypeEventTemplate,
    User,
)
from app.alert_dispatch import AlertKind
from app.notification_outbox import enqueue_staff
from fastapi import HTTPException
from app.firm_email_service import resolve_alert_transport

log = logging.getLogger(__name__)

SEP = "|"


def rad_event_key(calendar_id: uuid.UUID, uid: str) -> str:
    return f"r{SEP}{calendar_id}{SEP}{uid}"


def case_event_key(case_event_id: uuid.UUID) -> str:
    return f"c{SEP}{case_event_id}"


def parse_iso_to_anchor(iso_start: str, all_day: bool) -> tuple[date | None, datetime | None]:
    """Return (anchor_date, anchor_at_utc) for scheduling."""
    s = (iso_start or "").strip()
    if not s:
        return None, None
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            d = date.fromisoformat(s)
            return d, datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.date(), dt
    except ValueError:
        return None, None


def _subscription_for_user_event(db: Session, user_id: uuid.UUID, event_key: str) -> CalendarEventEmailAlertSubscription | None:
    return (
        db.execute(
            select(CalendarEventEmailAlertSubscription).where(
                CalendarEventEmailAlertSubscription.user_id == user_id,
                CalendarEventEmailAlertSubscription.event_key == event_key,
            )
        )
        .scalar_one_or_none()
    )


def user_has_email_alert(db: Session, user_id: uuid.UUID, event_key: str) -> bool:
    row = _subscription_for_user_event(db, user_id, event_key)
    return bool(row and row.enabled)


def enabled_email_alert_event_keys(db: Session, user_id: uuid.UUID) -> set[str]:
    rows = db.execute(
        select(CalendarEventEmailAlertSubscription.event_key).where(
            CalendarEventEmailAlertSubscription.user_id == user_id,
            CalendarEventEmailAlertSubscription.enabled.is_(True),
        )
    ).scalars().all()
    return set(rows)


def upsert_subscription(
    db: Session,
    *,
    user_id: uuid.UUID,
    event_key: str,
    enabled: bool,
    title: str,
    iso_start: str,
    all_day: bool,
    matter_template_id: uuid.UUID | None,
) -> None:
    anchor_date, anchor_at = parse_iso_to_anchor(iso_start, all_day)
    row = _subscription_for_user_event(db, user_id, event_key)
    now = datetime.now(timezone.utc)
    if not enabled:
        if row:
            row.enabled = False
            row.updated_at = now
            db.add(row)
        return
    if row is None:
        row = CalendarEventEmailAlertSubscription(
            id=uuid.uuid4(),
            user_id=user_id,
            event_key=event_key,
            enabled=True,
            anchor_date=anchor_date,
            anchor_at=anchor_at,
            all_day=all_day,
            title_snapshot=(title or "")[:600],
            matter_template_id=matter_template_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.enabled = True
        row.anchor_date = anchor_date
        row.anchor_at = anchor_at
        row.all_day = all_day
        row.title_snapshot = (title or "")[:600]
        row.matter_template_id = matter_template_id
        row.updated_at = now
        db.add(row)


def delete_subscriptions_for_event_key(db: Session, event_key: str) -> None:
    db.execute(delete(CalendarEventEmailAlertSubscription).where(CalendarEventEmailAlertSubscription.event_key == event_key))
    db.execute(delete(CalendarEventNotificationSent).where(CalendarEventNotificationSent.event_key == event_key))


def enrich_merged_calendar_events(db: Session, user: User, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    enabled_keys = enabled_email_alert_event_keys(db, user.id)
    for ev in events:
        ek: str | None = None
        cid = ev.get("calendar_id")
        uid = ev.get("uid")
        if cid and uid:
            try:
                ek = rad_event_key(uuid.UUID(str(cid)), str(uid))
            except ValueError:
                ek = None
        elif ev.get("case_event_id"):
            try:
                ek = case_event_key(uuid.UUID(str(ev["case_event_id"])))
            except ValueError:
                ek = None
        ev["email_alert_enabled"] = bool(ek and ek in enabled_keys)


def _reminder_offsets_days(n: int, unit: str, *, max_k: int = 12) -> list[int]:
    """Offsets before anchor date in days: k=1..max_k for 'every N [unit]'."""
    if n < 1:
        return []
    u = (unit or "").lower().strip()
    out: list[int] = []
    for k in range(1, max_k + 1):
        if u == "weeks":
            out.append(k * n * 7)
        elif u == "months":
            out.append(k * n * 30)
        else:
            out.append(k * n)
    return out


def _template_rules(db: Session, template_id: uuid.UUID | None) -> tuple[bool, int | None, str | None]:
    if not template_id:
        return True, None, None
    t = db.get(MatterSubTypeEventTemplate, template_id)
    if not t:
        return True, None, None
    return bool(t.notify_on_day), t.notify_every_n, t.notify_every_unit


def _should_fire(
    today: date,
    anchor: date | None,
    *,
    on_day: bool,
    every_n: int | None,
    every_unit: str | None,
) -> list[str]:
    """Return list of dedupe kinds to fire today (UTC date)."""
    if anchor is None:
        return []
    kinds: list[str] = []
    if on_day and today == anchor:
        kinds.append("on_day")
    if every_n and every_unit and every_n > 0:
        for i, days_back in enumerate(_reminder_offsets_days(every_n, every_unit), start=1):
            d = anchor - timedelta(days=days_back)
            if d == today:
                kinds.append(f"rep_{i}")
    return kinds


def process_due_calendar_notifications(db: Session) -> int:
    """Queue due reminders without network I/O; caller commits the batch."""

    today = datetime.now(timezone.utc).date()
    rows = (
        db.execute(
            select(CalendarEventEmailAlertSubscription).where(
                CalendarEventEmailAlertSubscription.enabled.is_(True),
            )
        )
        .scalars()
        .all()
    )
    sent_count = 0
    for sub in rows:
        user = db.get(User, sub.user_id)
        if not user or not user.is_active or not (user.email or "").strip():
            continue
        anchor = sub.anchor_date
        on_day, every_n, every_unit = _template_rules(db, sub.matter_template_id)
        kinds = _should_fire(
            today, anchor, on_day=on_day, every_n=every_n, every_unit=every_unit
        )
        for kind in kinds:
            exists = db.execute(
                select(CalendarEventNotificationSent.id).where(
                    CalendarEventNotificationSent.user_id == sub.user_id,
                    CalendarEventNotificationSent.event_key == sub.event_key,
                    CalendarEventNotificationSent.sent_day == today,
                    CalendarEventNotificationSent.kind == kind,
                )
            ).scalar_one_or_none()
            if exists:
                continue
            event_key = reminder_key(sub, today, kind)
            if (
                db.scalar(
                    select(NotificationOutbox.id).where(
                        NotificationOutbox.kind == "calendar_event_reminder",
                        NotificationOutbox.event_key == event_key,
                        NotificationOutbox.recipient_user_id == user.id,
                    )
                )
                is not None
            ):
                continue
            queued = enqueue_staff(
                db,
                kind=AlertKind.calendar_event_reminder,
                case_id=None,
                event_key=event_key,
                recipient_user_id=user.id,
                actor_id=None,
                context={
                    "title": sub.title_snapshot or "Event",
                    "anchor_label": anchor.isoformat() if anchor else "unknown",
                },
            )
            if queued is None:
                continue
            sent_count += 1
    return sent_count


def sync_case_event_subscription(
    db: Session,
    *,
    viewer_id: uuid.UUID,
    case_event: CaseEvent,
    email_alert: bool | None,
) -> None:
    if email_alert is None:
        return
    from app.event_service import _calendar_block_for_event

    title = case_event.name
    cs, _ce, cad = _calendar_block_for_event(case_event)
    upsert_subscription(
        db,
        user_id=viewer_id,
        event_key=case_event_key(case_event.id),
        enabled=email_alert,
        title=title,
        iso_start=cs or "",
        all_day=bool(cad),
        matter_template_id=case_event.template_id,
    )


def refresh_radicale_subscription_snapshot(
    db: Session, *, user_id: uuid.UUID, calendar_id: uuid.UUID, raw: dict[str, Any]
) -> None:
    """Refresh title/anchor/template for an enabled Radicale-backed subscription after any event edit."""
    uid = raw.get("uid")
    if not uid:
        return
    ek = rad_event_key(calendar_id, str(uid))
    row = _subscription_for_user_event(db, user_id, ek)
    if not row or not row.enabled:
        return
    mt_raw = raw.get("matter_template_id")
    tid: uuid.UUID | None = None
    if mt_raw:
        try:
            tid = uuid.UUID(str(mt_raw))
        except (ValueError, TypeError):
            tid = None
    upsert_subscription(
        db,
        user_id=user_id,
        event_key=ek,
        enabled=True,
        title=str(raw.get("title") or ""),
        iso_start=str(raw.get("start") or ""),
        all_day=bool(raw.get("all_day")),
        matter_template_id=tid,
    )


def refresh_case_event_subscription_snapshot(db: Session, *, viewer_id: uuid.UUID, case_event: CaseEvent) -> None:
    """If the viewer has an enabled subscription, refresh title/anchor after any case-event edit."""
    from app.event_service import _calendar_block_for_event

    ek = case_event_key(case_event.id)
    row = _subscription_for_user_event(db, viewer_id, ek)
    if not row or not row.enabled:
        return
    cs, _ce, cad = _calendar_block_for_event(case_event)
    upsert_subscription(
        db,
        user_id=viewer_id,
        event_key=ek,
        enabled=True,
        title=case_event.name,
        iso_start=cs or "",
        all_day=bool(cad),
        matter_template_id=case_event.template_id,
    )


def reminder_fingerprint(sub):
    values = [
        sub.event_key,
        str(sub.anchor_date),
        str(sub.anchor_at),
        sub.title_snapshot,
        str(sub.matter_template_id),
        bool(sub.all_day),
    ]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def reminder_key(sub, day, kind):
    return f"{sub.id}:{day.isoformat()}:{kind}:{reminder_fingerprint(sub)}"


def require_reminder_access(db, row, recipient):
    """Fail closed for revoked, changed or expired calendar subscriptions."""
    from app.calendar_service import resolve_calendar_access
    from app.deps import require_case_access

    try:
        sid, day, kind, fingerprint = row.event_key.split(":")
        sub = db.get(CalendarEventEmailAlertSubscription, uuid.UUID(sid))
        today = datetime.now(timezone.utc).date()
        if (
            sub is None
            or not sub.enabled
            or sub.user_id != recipient.id
            or day != today.isoformat()
            or fingerprint != reminder_fingerprint(sub)
        ):
            raise ValueError("Stale subscription")
        on_day, every_n, every_unit = _template_rules(db, sub.matter_template_id)
        if kind not in _should_fire(
            today,
            sub.anchor_date,
            on_day=on_day,
            every_n=every_n,
            every_unit=every_unit,
        ):
            raise ValueError("Reminder no longer due")
        parts = sub.event_key.split(SEP, 2)
        if parts[0] == "c" and len(parts) == 2:
            event = db.get(CaseEvent, uuid.UUID(parts[1]))
            if event is None:
                raise ValueError("Event removed")
            require_case_access(event.case_id, recipient, db)
        elif parts[0] == "r" and len(parts) == 3:
            resolve_calendar_access(db, recipient, uuid.UUID(parts[1]))
        else:
            raise ValueError("Unknown calendar source")
    except (ValueError, TypeError):
        raise HTTPException(403, "Reminder subscription changed or expired") from None

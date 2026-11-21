"""Aggregate-only queue diagnostics: no addresses, message bodies or event identities."""

from datetime import timezone
from sqlalchemy import select, func
from app.models import NotificationOutbox, NotificationAttempt
from app.notification_outbox import STALE_AFTER
from app.timeutil import utcnow

STATES = ("pending", "sending", "sent", "failed", "uncertain", "cancelled")


def diagnostics(db):
    now = utcnow()
    states = {state: 0 for state in STATES}
    states.update(
        dict(
            db.execute(
                select(NotificationOutbox.state, func.count()).group_by(
                    NotificationOutbox.state
                )
            ).all()
        )
    )
    oldest = db.scalar(
        select(func.min(NotificationOutbox.created_at)).where(
            NotificationOutbox.state == "pending"
        )
    )
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    stale = db.scalar(
        select(func.count())
        .select_from(NotificationOutbox)
        .where(
            NotificationOutbox.state == "sending",
            NotificationOutbox.updated_at <= now - STALE_AFTER,
        )
    )
    attempts = db.scalar(select(func.count()).select_from(NotificationAttempt))
    return {
        "states": states,
        "oldest_pending_age_seconds": (
            max(0, int((now - oldest).total_seconds())) if oldest else None
        ),
        "stale_sending": stale,
        "attempts": attempts,
        "attention_required": bool(states["failed"] or states["uncertain"] or stale),
        "delivery_mode": "on-demand",
        "sent_means": "provider_accepted",
    }

"""SQLAlchemy models — calendar domain."""
from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    LargeBinary,
    Time,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

class UserCalendar(Base):
    """Logical calendar: Radicale collection under owner's principal at /{owner_id}/{radicale_slug}/."""

    __tablename__ = "user_calendar"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Radicale calendar collection id (directory name); stable after create.
    radicale_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Optional fill for events with no category (in-app display only; not written to CalDAV).
    default_event_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class UserCalendarShare(Base):
    __tablename__ = "user_calendar_share"

    calendar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_calendar.id", ondelete="CASCADE"), primary_key=True
    )
    grantee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    can_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

class UserCalendarSubscription(Base):
    """Subscriber added a public calendar to their Canary calendar list (read-only in v1)."""

    __tablename__ = "user_calendar_subscription"

    subscriber_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    calendar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_calendar.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class UserCalendarCategory(Base):
    """Canary-only category; owner defines list; colour drives in-app FullCalendar display."""

    __tablename__ = "user_calendar_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calendar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_calendar.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # #RRGGBB or null (default event styling in UI).
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CalendarEventCategory(Base):
    """Maps iCalendar UID + logical calendar to a category (not stored in Radicale)."""

    __tablename__ = "calendar_event_category"

    calendar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_calendar.id", ondelete="CASCADE"), primary_key=True
    )
    event_uid: Mapped[str] = mapped_column(String(512), primary_key=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_calendar_category.id", ondelete="SET NULL"), nullable=True
    )

class CalendarEventEmailAlertSubscription(Base):
    """Per-user opt-in to e-mail reminders for one calendar row (Radicale UID or synthetic case event)."""

    __tablename__ = "calendar_event_email_alert_subscription"
    __table_args__ = (UniqueConstraint("user_id", "event_key", name="uq_cal_ev_mail_sub_user_event"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    event_key: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    anchor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    title_snapshot: Mapped[str] = mapped_column(String(600), nullable=False, default="")
    matter_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type_event_template.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CalendarEventNotificationSent(Base):
    """Dedupe bucket for one reminder send (user + logical event + UTC day + kind)."""

    __tablename__ = "calendar_event_notification_sent"
    __table_args__ = (
        UniqueConstraint("user_id", "event_key", "sent_day", "kind", name="uq_cal_ev_notif_sent_dedupe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    event_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sent_day: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

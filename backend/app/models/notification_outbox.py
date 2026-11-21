import uuid
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.timeutil import utcnow


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','sending','sent','failed','uncertain','cancelled')",
            name="ck_notification_state",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    event_key: Mapped[str] = mapped_column(String(240), nullable=False)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payload_enc: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class NotificationAttempt(Base):
    __tablename__ = "notification_attempt"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    transport: Mapped[str | None] = mapped_column(String(16), nullable=True)
    code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at = mapped_column(DateTime(timezone=True), nullable=True)

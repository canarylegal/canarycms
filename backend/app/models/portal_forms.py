"""SQLAlchemy models — portal_forms domain."""
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

class PortalFormFieldType(str, enum.Enum):
    section = "section"
    text = "text"
    textarea = "textarea"
    date = "date"
    select = "select"
    file = "file"

class PortalFormSubmissionStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    voided = "voided"
    superseded = "superseded"

class PortalFormTemplate(Base):
    """Firm-wide portal form precedents scoped by matter type (like fee scales)."""

    __tablename__ = "portal_form_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    matter_head_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_head_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    matter_sub_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("reference", name="uq_portal_form_template_reference"),)

class PortalFormTemplateField(Base):
    __tablename__ = "portal_form_template_field"
    __table_args__ = (UniqueConstraint("template_id", "field_key", name="uq_portal_form_template_field_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portal_form_template.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    field_type: Mapped[PortalFormFieldType] = mapped_column(
        Enum(PortalFormFieldType, name="portal_form_field_type"),
        nullable=False,
    )
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    select_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

class PortalFormSubmission(Base):
    __tablename__ = "portal_form_submission"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portal_form_template.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact_portal_grant.id", ondelete="SET NULL"), nullable=True
    )
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portal_form_submission.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[PortalFormSubmissionStatus] = mapped_column(
        Enum(PortalFormSubmissionStatus, name="portal_form_submission_status"),
        nullable=False,
        default=PortalFormSubmissionStatus.pending,
    )
    responses: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    snapshot_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

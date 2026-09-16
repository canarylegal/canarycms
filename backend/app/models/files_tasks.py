"""SQLAlchemy models — files_tasks domain."""
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

class FileCategory(str, enum.Enum):
    case_document = "case_document"
    precedent = "precedent"
    fee_scale = "fee_scale"
    system = "system"
    firm_letterhead = "firm_letterhead"
    firm_portal_logo = "firm_portal_logo"
    firm_default_signature = "firm_default_signature"
    user_signature = "user_signature"

class File(Base):
    __tablename__ = "file"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id"), nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    category: Mapped[FileCategory] = mapped_column(Enum(FileCategory, name="file_category"), nullable=False)

    # Virtual folder path inside the case's documents tree ("" == root).
    folder_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # "Pinned" controls whether the file is shown in the pinned section.
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Optional parent/child relationship for grouped artifacts in the UI.
    # Used by the Roundcube "file email into case" feature:
    # an email (.eml) becomes the parent, and each MIME attachment becomes a child.
    parent_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # When a message is filed from Roundcube, we keep IMAP location so Canary can
    # open the live message in Roundcube (_extwin=1) while it still exists on the server.
    source_imap_mbox: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_imap_uid: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Parsed from parent .eml on upload (message/rfc822); UI second line in document list.
    source_mail_from_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_mail_from_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True if message was filed from a sent/outbox folder (or from-address matches uploader). None = unknown.
    source_mail_is_outbound: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # RFC5322 Message-ID header value (angle brackets optional), parsed from parent .eml on upload.
    source_internet_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RFC5322 Date header from root .eml / rfc822 (parsed on upload & refresh); UI “Created” for e-mail.
    source_mail_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Outlook thread id (Office.js ``conversationId``) when filing from read mode — used to match replies on send.
    source_outlook_conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Outlook/Exchange REST item id from the Office add-in when filing from Outlook (OWA read deeplink).
    source_outlook_item_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Microsoft Graph message id (often same string as REST item id) — OWA read deeplink / desktop open.
    outlook_graph_message_id: Mapped[str | None] = mapped_column(String(450), nullable=True)
    # Graph ``webLink`` when available (preferred one-click open in the browser).
    outlook_web_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True for new docs from compose-office until the user finishes OnlyOffice "Save & Close" (published).
    oo_compose_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set while /oo-force-save waits for DS callback; cleared when bytes are saved or unchanged save is ack'd.
    oo_force_save_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_via_portal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_portal_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class FileEditSession(Base):
    """Short-lived WebDAV edit lease for a single case file (desktop editors, e.g. ONLYOFFICE)."""

    __tablename__ = "file_edit_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("file.id", ondelete="CASCADE"), nullable=False)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Small metadata (never secrets); stored as JSON string for now to avoid adding JSONB dependency immediately.
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CaseNote(Base):
    __tablename__ = "case_note"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id"), nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)

    body: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CaseTaskStatus(str, enum.Enum):
    open = "open"
    done = "done"
    cancelled = "cancelled"

class CaseTaskPriority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"

class MatterSubTypeStandardTask(Base):
    """Admin-defined task titles suggested when creating a case task for a matter sub-type."""

    __tablename__ = "matter_sub_type_standard_task"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_sub_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CaseTask(Base):
    __tablename__ = "case_task"
    __table_args__ = (
        Index(
            "uq_case_task_case_event_id",
            "case_event_id",
            unique=True,
            postgresql_where=text("case_event_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CaseTaskStatus] = mapped_column(
        Enum(CaseTaskStatus, name="case_task_status"),
        nullable=False,
        default=CaseTaskStatus.open,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    standard_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type_standard_task.id", ondelete="SET NULL"), nullable=True
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    case_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_event.id", ondelete="CASCADE"), nullable=True
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CaseTimeEntryStatus(str, enum.Enum):
    unbilled = "unbilled"
    billed = "billed"
    written_off = "written_off"

class CaseTimeEntry(Base):
    """Fee-earner time logged against a matter (6-minute units); Phase 1: unbilled only."""

    __tablename__ = "case_time_entry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CaseTimeEntryStatus] = mapped_column(
        Enum(CaseTimeEntryStatus, name="case_time_entry_status"),
        nullable=False,
        default=CaseTimeEntryStatus.unbilled,
    )
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_invoice_line.id", ondelete="SET NULL"), nullable=True, index=True
    )
    non_billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

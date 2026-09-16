"""SQLAlchemy models — signing domain."""
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

class DocusignDocumentTier(str, enum.Enum):
    a = "a"
    b = "b"
    c = "c"

class DocusignSignatureLevel(str, enum.Enum):
    standard = "standard"
    wes = "wes"
    qes = "qes"

class DocusignSigningStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    declined = "declined"
    voided = "voided"
    expired = "expired"
    error = "error"

class DocusignRecipientStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    completed = "completed"
    declined = "declined"
    autoresponded = "autoresponded"

class DocusignIntegrationSettings(Base):
    """Singleton (id=1): firm DocuSign API credentials and feature toggles."""

    __tablename__ = "docusign_integration_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    use_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_tier_a: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_tier_b: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_tier_c: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_wes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_qes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    account_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    integration_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rsa_private_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    connect_hmac_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_base_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_standard_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_wes_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_qes_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class DocusignSigningRequest(Base):
    __tablename__ = "docusign_signing_request"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("docusign_signing_request.id", ondelete="SET NULL"), nullable=True
    )
    docusign_envelope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    docusign_template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    envelope_subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    document_tier: Mapped[DocusignDocumentTier] = mapped_column(
        Enum(DocusignDocumentTier, name="docusign_document_tier"),
        nullable=False,
        default=DocusignDocumentTier.a,
    )
    signature_level: Mapped[DocusignSignatureLevel] = mapped_column(
        Enum(DocusignSignatureLevel, name="docusign_signature_level"),
        nullable=False,
        default=DocusignSignatureLevel.standard,
    )
    status: Mapped[DocusignSigningStatus] = mapped_column(
        Enum(DocusignSigningStatus, name="docusign_signing_status"),
        nullable=False,
        default=DocusignSigningStatus.pending,
    )
    signed_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    certificate_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ledger_pair_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class DocusignSigningRecipient(Base):
    __tablename__ = "docusign_signing_recipient"
    __table_args__ = (UniqueConstraint("sign_token", name="uq_docusign_signing_recipient_sign_token"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signing_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("docusign_signing_request.id", ondelete="CASCADE"), nullable=False
    )
    case_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_contact.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    routing_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    role_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    docusign_recipient_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sign_token: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocusignRecipientStatus] = mapped_column(
        Enum(DocusignRecipientStatus, name="docusign_recipient_status"),
        nullable=False,
        default=DocusignRecipientStatus.pending,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CanarySignStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    declined = "declined"
    voided = "voided"
    expired = "expired"

class CanarySignRecipientStatus(str, enum.Enum):
    pending = "pending"
    viewed = "viewed"
    signed = "signed"
    declined = "declined"

class CanarySignOrderMode(str, enum.Enum):
    parallel = "parallel"
    sequential = "sequential"

class CanarySignFieldType(str, enum.Enum):
    signature = "signature"
    initials = "initials"
    date = "date"
    printed_name = "printed_name"
    checkbox = "checkbox"

class CanarySignAuditEventType(str, enum.Enum):
    created = "created"
    sent = "sent"
    viewed = "viewed"
    signed = "signed"
    declined = "declined"
    voided = "voided"
    reminded = "reminded"
    completed = "completed"
    expired = "expired"
    form_locked = "form_locked"
    form_filled = "form_filled"

class CanarySignRequest(Base):
    __tablename__ = "canary_sign_request"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    signed_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    certificate_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canary_sign_request.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[CanarySignStatus] = mapped_column(
        Enum(CanarySignStatus, name="canary_sign_status"),
        nullable=False,
        default=CanarySignStatus.pending,
    )
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_mode: Mapped[CanarySignOrderMode] = mapped_column(
        Enum(CanarySignOrderMode, name="canary_sign_order_mode"),
        nullable=False,
        default=CanarySignOrderMode.parallel,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    has_fillable_form: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    form_locked_by_recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canary_sign_recipient.id", ondelete="SET NULL"), nullable=True
    )
    form_locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_responses: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CanarySignRecipient(Base):
    __tablename__ = "canary_sign_recipient"
    __table_args__ = (UniqueConstraint("sign_token", name="uq_canary_sign_recipient_sign_token"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signing_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canary_sign_request.id", ondelete="CASCADE"), nullable=False
    )
    case_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_contact.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    routing_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sign_token: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[CanarySignRecipientStatus] = mapped_column(
        Enum(CanarySignRecipientStatus, name="canary_sign_recipient_status"),
        nullable=False,
        default=CanarySignRecipientStatus.pending,
    )
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class CanarySignField(Base):
    __tablename__ = "canary_sign_field"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signing_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canary_sign_request.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canary_sign_recipient.id", ondelete="CASCADE"), nullable=False
    )
    field_type: Mapped[CanarySignFieldType] = mapped_column(
        Enum(CanarySignFieldType, name="canary_sign_field_type"),
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    placement_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="free")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    x_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    w_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    h_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class CanarySignAuditEvent(Base):
    __tablename__ = "canary_sign_audit_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signing_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canary_sign_request.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canary_sign_recipient.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[CanarySignAuditEventType] = mapped_column(
        Enum(CanarySignAuditEventType, name="canary_sign_audit_event_type"),
        nullable=False,
    )
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

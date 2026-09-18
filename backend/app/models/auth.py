"""SQLAlchemy models — auth domain."""
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

class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"

class UserPermissionCategory(Base):
    """Admin-defined permission set; optional FK from user.permission_category_id."""

    __tablename__ = "user_permission_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    perm_fee_earner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    perm_post_client: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    perm_post_office: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    perm_post_anticipated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    perm_approve_payments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    perm_approve_invoices: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    perm_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    initials: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    job_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.user)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    permission_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_permission_category.id", ondelete="SET NULL"), nullable=True
    )

    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_token_version: Mapped[int] = mapped_column(nullable=False, default=1)

    # Fernet-encrypted CalDAV app password (Radicale htpasswd); plaintext shown only on enable/reset.
    caldav_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Matter e-mail compose: desktop mailto vs Outlook on the web (user setting).
    email_launch_preference: Mapped[str] = mapped_column(String(32), nullable=False, default="desktop")
    email_outlook_web_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When email_launch_preference is desktop: Outlook (Graph handoff) vs Thunderbird/other (mailto only).
    email_desktop_client: Mapped[str] = mapped_column(String(32), nullable=False, default="outlook")

    appearance_font: Mapped[str | None] = mapped_column(Text, nullable=True)
    appearance_accent: Mapped[str] = mapped_column(String(7), nullable=False, default="#f0d010")
    appearance_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="light")
    appearance_page_bg: Mapped[str | None] = mapped_column(String(7), nullable=True)

    ui_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Billing: charge-out rate for time / WIP (pence per hour); set in Admin → Users.
    charge_rate_pence_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)

    signature_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    # Composed signature image width: 1–10 (7 = 2 inches wide, the historical default).
    signature_scale: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    # Next Outlook send (add-in OnMessageSend): matter chosen from Canary web before composing.
    outlook_pending_send_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="SET NULL"), nullable=True
    )
    outlook_pending_send_source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    outlook_pending_send_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Canary web → Outlook add-in: open compose with merge + attachments (Phase 3 handoff).
    outlook_pending_compose_handoff_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    outlook_pending_compose_handoff_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class RoundcubeSsoTokenUse(Base):
    __tablename__ = "roundcube_sso_token_use"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class PasswordResetToken(Base):
    """Single-use staff password reset link (hashed token, short TTL)."""

    __tablename__ = "password_reset_token"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class AuthRateLimitEntry(Base):
    """Failed auth / reset attempts keyed by scope + identifier (email or IP)."""

    __tablename__ = "auth_rate_limit_entry"
    __table_args__ = (UniqueConstraint("scope", "identifier", name="uq_auth_rate_limit_scope_identifier"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    identifier: Mapped[str] = mapped_column(String(320), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class WebAuthnChallenge(Base):
    """Short-lived WebAuthn ceremony challenges (registration / passkey login)."""

    __tablename__ = "webauthn_challenge"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    challenge_b64: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class WebAuthnCredential(Base):
    """Registered passkey / WebAuthn credential for a user."""

    __tablename__ = "webauthn_credential"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transports: Mapped[str | None] = mapped_column(String(200), nullable=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("credential_id", name="uq_webauthn_credential_credential_id"),)

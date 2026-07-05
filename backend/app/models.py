import enum
import uuid
from decimal import Decimal
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
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
from sqlalchemy.orm import Mapped, mapped_column

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
    appearance_accent: Mapped[str] = mapped_column(String(7), nullable=False, default="#2563eb")
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


class MatterHeadType(Base):
    __tablename__ = "matter_head_type"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    # When True, non-admin pickers hide this head; cases may still reference it. Admins toggle per firm.
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MatterSubType(Base):
    __tablename__ = "matter_sub_type"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    head_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_head_type.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MatterSubTypeMenu(Base):
    __tablename__ = "matter_sub_type_menu"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sub_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    archived = "archived"
    quote = "quote"
    quote_closed = "quote_closed"
    post_completion = "post_completion"


class CaseLockMode(str, enum.Enum):
    none = "none"
    open_by_default = "open_by_default"
    allow_list = "allow_list"


class CaseAccessMode(str, enum.Enum):
    allow = "allow"
    deny = "deny"


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


class RoundcubeSsoTokenUse(Base):
    __tablename__ = "roundcube_sso_token_use"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MatterContactTypeConfig(Base):
    """Admin-configurable labels for matter contact type slugs on ``case_contact.matter_contact_type``."""

    __tablename__ = "matter_contact_type_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Case(Base):
    __tablename__ = "case"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # Matter description
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Client name(s) denormalized for the main menu; snapshots still live in case_contact.
    client_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fee_earner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, name="case_status"), nullable=False, default=CaseStatus.open)
    practice_area: Mapped[str | None] = mapped_column(String(200), nullable=True)
    matter_head_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_head_type.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matter_sub_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_mode: Mapped[CaseLockMode] = mapped_column(
        Enum(CaseLockMode, name="case_lock_mode"),
        nullable=False,
        default=CaseLockMode.open_by_default,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_source.id", ondelete="SET NULL"), nullable=True, index=True
    )
    portal_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseSource(Base):
    """Referral / work source labels (Quotes page Sources database)."""

    __tablename__ = "case_source"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseQuoteSnapshot(Base):
    """Stored quote line amounts at compose time (for Finance auto-fill)."""

    __tablename__ = "case_quote_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    quote_lines: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseReferenceCounter(Base):
    __tablename__ = "case_reference_counter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CasePropertyDetails(Base):
    """Per-case Property menu data (UK or free-form address + title numbers). Payload is JSON."""

    __tablename__ = "case_property_details"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), primary_key=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class LetterheadStyle(str, enum.Enum):
    """Letter compose: physical pre-printed stock vs digital header/footer template."""

    preprinted = "preprinted"
    digital = "digital"


class PrecedentKind(str, enum.Enum):
    letter = "letter"
    email = "email"
    document = "document"


class PrecedentCategory(Base):
    __tablename__ = "precedent_category"
    __table_args__ = (UniqueConstraint("matter_sub_type_id", "name", name="uq_precedent_category_sub_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_sub_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FirmSettings(Base):
    """Singleton firm-wide configuration (id must always be 1)."""

    __tablename__ = "firm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    trading_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    registered_company_name: Mapped[str | None] = mapped_column(String(400), nullable=True)
    addr_line1: Mapped[str | None] = mapped_column(String(300), nullable=True)
    addr_line2: Mapped[str | None] = mapped_column(String(300), nullable=True)
    town_city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    county: Mapped[str | None] = mapped_column(String(150), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    letterhead_style: Mapped[LetterheadStyle] = mapped_column(
        Enum(LetterheadStyle, name="letterhead_style"),
        nullable=False,
        default=LetterheadStyle.preprinted,
    )
    letterhead_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    quote_letterhead_style: Mapped[LetterheadStyle] = mapped_column(
        Enum(LetterheadStyle, name="letterhead_style"),
        nullable=False,
        default=LetterheadStyle.preprinted,
    )
    quote_letterhead_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    portal_logo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    invoice_template_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    mandate_two_factor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mandate_password_rotation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_rotation_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    client_bank_account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    client_bank_sort_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    client_bank_account_number_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    client_bank_account_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ReconciliationStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"


class ClientAccountReconciliation(Base):
    """Month-end client account reconciliation snapshot (one row per period end date)."""

    __tablename__ = "client_account_reconciliation"
    __table_args__ = (UniqueConstraint("period_end_date", name="uq_client_account_reconciliation_period_end"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    ledger_client_total_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    ledger_office_total_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    bank_statement_balance_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    difference_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    prepared_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status"),
        nullable=False,
        default=ReconciliationStatus.draft,
    )


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


class MergeCodeCatalog(Base):
    """Editable descriptions for precedent merge tokens; keys mirror ``docx_util.PRECEDENT_CODES``."""

    __tablename__ = "merge_code_catalog"

    code: Mapped[str] = mapped_column(String(160), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class Precedent(Base):
    __tablename__ = "precedent"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[PrecedentKind] = mapped_column(Enum(PrecedentKind, name="precedent_kind"), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("file.id", ondelete="CASCADE"), nullable=False)
    # Scope: (NULL,NULL,NULL) = all cases; (H,NULL,NULL) = all sub-types under head H; (H,S,NULL) = all categories under sub S; (H,S,C) = one category.
    matter_head_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_head_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    matter_sub_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("precedent_category.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FeeScale(Base):
    """Firm-wide fee scale templates used when composing quotes."""

    __tablename__ = "fee_scale"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    vat_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    # Scope: (NULL,NULL) = all cases; (H,NULL) = all sub-types under head H; (H,S) = one sub-type.
    matter_head_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_head_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    matter_sub_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("reference", name="uq_fee_scale_reference"),)


class UserFeeScaleFavorite(Base):
    """Per-user starred fee scales for quick quote selection."""

    __tablename__ = "user_fee_scale_favorite"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fee_scale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "fee_scale_id", name="uq_user_fee_scale_favorite"),)


class FeeScaleLineKind(str, enum.Enum):
    section_header = "section_header"
    item = "item"
    vat = "vat"
    subtotal = "subtotal"
    total = "total"


class FeeScaleAmountKind(str, enum.Enum):
    fixed = "fixed"
    editable = "editable"
    band = "band"


class FeeScaleVatTreatment(str, enum.Enum):
    """How VAT applies to a line item amount."""

    included = "included"  # Including / No VAT — amount is final; no separate VAT column
    plus_vat = "plus_vat"  # Plus VAT — amount is net; VAT shown in VAT column


class FeeScaleCategory(Base):
    __tablename__ = "fee_scale_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fee_scale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FeeScaleBandSet(Base):
    __tablename__ = "fee_scale_band_set"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fee_scale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FeeScaleBandRow(Base):
    __tablename__ = "fee_scale_band_row"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    band_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale_band_set.id", ondelete="CASCADE"), nullable=False, index=True
    )
    min_value_pence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_value_pence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FeeScaleLine(Base):
    __tablename__ = "fee_scale_line"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale_category.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    line_kind: Mapped[FeeScaleLineKind] = mapped_column(
        Enum(FeeScaleLineKind, name="fee_scale_line_kind"), nullable=False
    )
    amount_kind: Mapped[FeeScaleAmountKind | None] = mapped_column(
        Enum(FeeScaleAmountKind, name="fee_scale_amount_kind"), nullable=True
    )
    default_amount_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    band_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale_band_set.id", ondelete="SET NULL"), nullable=True
    )
    vat_treatment: Mapped[FeeScaleVatTreatment] = mapped_column(
        Enum(FeeScaleVatTreatment, name="fee_scale_vat_treatment"),
        nullable=False,
        default=FeeScaleVatTreatment.included,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseAccessRule(Base):
    __tablename__ = "case_access_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    mode: Mapped[CaseAccessMode] = mapped_column(Enum(CaseAccessMode, name="case_access_mode"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ContactType(str, enum.Enum):
    person = "person"
    organisation = "organisation"


class Contact(Base):
    __tablename__ = "contact"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[ContactType] = mapped_column(Enum(ContactType, name="contact_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Person name fields (type == 'person')
    title: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Organisation name fields (type == 'organisation')
    company_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    trading_name: Mapped[str | None] = mapped_column(String(300), nullable=True)

    address_line1: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    county: Mapped[str | None] = mapped_column(String(150), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ContactPortalAccess(Base):
    """Portal login for a global contact (unique access code per contact)."""

    __tablename__ = "contact_portal_access"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    code_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notify_files_added: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_folder_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ContactPortalGrant(Base):
    """Folder-scoped portal access for a contact (many grants per contact)."""

    __tablename__ = "contact_portal_grant"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    folder_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    can_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_upload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CasePortalStaffRecipient(Base):
    """Staff users who receive portal notification e-mails for a matter."""

    __tablename__ = "case_portal_staff_recipient"

    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class PortalActivityEvent(Base):
    __tablename__ = "portal_activity_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact_portal_grant.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class QuotePortalDeliveryStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    superseded = "superseded"


class QuotePortalDelivery(Base):
    """Quote sent to a portal contact for accept/decline."""

    __tablename__ = "quote_portal_delivery"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("file.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact_portal_grant.id", ondelete="SET NULL"), nullable=True
    )
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    file_version_at_send: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[QuotePortalDeliveryStatus] = mapped_column(
        Enum(QuotePortalDeliveryStatus, name="quote_portal_delivery_status"),
        nullable=False,
        default=QuotePortalDeliveryStatus.pending,
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    portal_pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True, index=True
    )


class PortalLoginOtp(Base):
    __tablename__ = "portal_login_otp"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False)
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MailPluginAuthCode(Base):
    """Single-use code issued after staff approves a mail add-in connection."""

    __tablename__ = "mail_plugin_auth_code"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    client: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseContact(Base):
    __tablename__ = "case_contact"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id"), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True
    )
    is_linked_to_master: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    type: Mapped[ContactType] = mapped_column(Enum(ContactType, name="contact_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Person name fields (type == 'person')
    title: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Organisation name fields (type == 'organisation')
    company_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    trading_name: Mapped[str | None] = mapped_column(String(300), nullable=True)

    address_line1: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    county: Mapped[str | None] = mapped_column(String(150), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Matter-only fields (not pushed to global Contact when editing snapshot).
    matter_contact_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    matter_contact_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # For matter_contact_type == "lawyers": up to four linked Client matter contacts (UUID strings in JSON).
    lawyer_client_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    letter_salutation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    letter_salutation_custom: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FileCategory(str, enum.Enum):
    case_document = "case_document"
    precedent = "precedent"
    fee_scale = "fee_scale"
    system = "system"
    firm_letterhead = "firm_letterhead"
    firm_portal_logo = "firm_portal_logo"
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


# ---------------------------------------------------------------------------
# Ledger (SAR 2019)
# ---------------------------------------------------------------------------

class LedgerAccountType(str, enum.Enum):
    client = "client"
    office = "office"


class LedgerDirection(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class LedgerAccount(Base):
    """One client account + one office account per case, created on first access."""

    __tablename__ = "ledger_account"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    account_type: Mapped[LedgerAccountType] = mapped_column(
        Enum(LedgerAccountType, name="ledger_account_type"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class LedgerEntry(Base):
    """Single leg of a double-entry posting; two rows share the same pair_id."""

    __tablename__ = "ledger_entry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_account.id", ondelete="CASCADE"), nullable=False
    )
    pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    direction: Mapped[LedgerDirection] = mapped_column(
        Enum(LedgerDirection, name="ledger_direction"), nullable=False
    )
    # Stored in integer pence to avoid floating-point errors.
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    case_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_contact.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True, index=True
    )
    posted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_anticipated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anticipated_for_date: Mapped[date | None] = mapped_column(Date, nullable=True)


# ---------------------------------------------------------------------------
# Finance templates (admin-defined per matter sub-type) + case-level finance
# ---------------------------------------------------------------------------

class FinanceCategoryTemplate(Base):
    """Admin-defined category within a matter sub-type's finance template."""

    __tablename__ = "finance_category_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_sub_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FinanceItemTemplate(Base):
    """Admin-defined debit/credit line item within a finance category template."""

    __tablename__ = "finance_item_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_category_template.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "debit" | "credit"
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FinanceCategory(Base):
    """Case-specific finance category; may originate from a template or be custom."""

    __tablename__ = "finance_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    template_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_category_template.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class FinanceItem(Base):
    """Case-specific finance line item; may originate from a template or be custom."""

    __tablename__ = "finance_item"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_category.id", ondelete="CASCADE"), nullable=False
    )
    template_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finance_item_template.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "debit" | "credit"
    amount_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vat_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vat_treatment: Mapped[FeeScaleVatTreatment | None] = mapped_column(
        Enum(FeeScaleVatTreatment, name="fee_scale_vat_treatment"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Sub-menu: Events (admin template per matter sub-type + per-case dated rows)
# ---------------------------------------------------------------------------


class MatterSubTypeEventTemplate(Base):
    """Admin-defined event label for a matter sub-type (order + name + e-mail reminder defaults)."""

    __tablename__ = "matter_sub_type_event_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_sub_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notify_on_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_every_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notify_every_unit: Mapped[str | None] = mapped_column(String(12), nullable=True)  # days | weeks | months
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseEvent(Base):
    """Per-case event row (seeded from template); user sets event_date."""

    __tablename__ = "case_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type_event_template.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    event_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    track_in_calendar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calendar_event_uid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class InvoiceSeq(Base):
    """Single-row sequence for global invoice numbers."""

    __tablename__ = "invoice_seq"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    next_num: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class BillingSettings(Base):
    """Singleton row (id=1): default VAT % for new invoice lines."""

    __tablename__ = "billing_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    default_vat_percent: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, default=Decimal("20"))


class EmailIntegrationSettings(Base):
    """Singleton row (id=1): mailto vs Microsoft Graph; optional Entra app credentials (secret encrypted)."""

    __tablename__ = "email_integration_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    integration_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="microsoft_graph")
    graph_tenant_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    outlook_web_mail_base: Mapped[str | None] = mapped_column(Text, nullable=True)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alert_transport: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    graph_send_mailbox: Mapped[str | None] = mapped_column(String(320), nullable=True)
    graph_send_from_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class SmtpNotificationSettings(Base):
    """Singleton (id=1): outbound SMTP for calendar (and future) e-mail alerts."""

    __tablename__ = "smtp_notification_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    host: Mapped[str | None] = mapped_column(String(300), nullable=True)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    username: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


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


class BillingLineTemplate(Base):
    """Admin-defined default fee / disbursement labels and amounts per matter sub-type."""

    __tablename__ = "billing_line_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_sub_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="CASCADE"), nullable=False
    )
    line_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "fee" | "disbursement"
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    default_amount_pence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseInvoice(Base):
    __tablename__ = "case_invoice"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    ledger_pair_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reversal_pair_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_pence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payee_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    credit_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CaseInvoiceLine(Base):
    __tablename__ = "case_invoice_line"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_invoice.id", ondelete="CASCADE"), nullable=False
    )
    line_type: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount_pence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_pence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )


class CaseDocsView(Base):
    """Per-user timestamp of when they last viewed a case's documents."""

    __tablename__ = "case_docs_view"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case.id", ondelete="CASCADE"), primary_key=True
    )
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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

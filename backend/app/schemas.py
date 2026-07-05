from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    CaseLockMode,
    CaseStatus,
    CaseTaskStatus,
    ContactType,
    FileCategory,
    LetterheadStyle,
    PrecedentKind,
    UserRole,
)
from app.user_initials import normalize_initials
from app.user_ui_preferences import UserUiPreferencesOut


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PluginAuthorizeIn(BaseModel):
    client: Literal["thunderbird", "outlook"]
    state: str = Field(min_length=16, max_length=128)
    redirect_uri: str = Field(min_length=1, max_length=2048)


class PluginAuthorizeOut(BaseModel):
    code: str


class PluginTokenIn(BaseModel):
    client: Literal["thunderbird", "outlook"]
    state: str = Field(min_length=16, max_length=128)
    code: str | None = Field(default=None, max_length=256)


class UserAppearanceOut(BaseModel):
    font: str = ""
    accent: str = "#2563eb"
    mode: Literal["light", "dark"] = "light"
    page_bg: str = ""


class UserAppearanceUpdate(BaseModel):
    font: str = Field(default="", max_length=500)
    accent: str = Field(default="#2563eb", max_length=7)
    mode: Literal["light", "dark"] = "light"
    page_bg: str = Field(default="", max_length=7)


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    initials: str
    job_title: str | None = None
    role: UserRole
    is_active: bool
    is_2fa_enabled: bool
    is_master_recovery: bool = Field(
        default=False,
        description="True for the env-configured master recovery operator (not a firm staff account).",
    )
    pending_authenticator_setup: bool = Field(
        default=False,
        description="True when TOTP setup was started but not yet confirmed (requires password to resume).",
    )
    organization_requires_second_factor: bool = False
    has_passkeys: bool = False
    email_launch_preference: Literal["desktop", "outlook_web"] = "desktop"
    email_outlook_web_url: str | None = None
    email_desktop_client: Literal["outlook", "other"] = "outlook"
    email_integration_mode: Literal["mailto", "microsoft_graph"] = "microsoft_graph"
    m365_graph_drafts_configured: bool = False
    admin_console_access: bool = Field(
        default=False,
        description="User may open the admin console (built-in admin or category Admin permission).",
    )
    accounts_workspace_access: bool = Field(
        default=False,
        description="User may open the firm-wide Accounts desk (admin or cashier approve permissions).",
    )
    session_second_factor_verified: bool = Field(
        default=True,
        description=(
            "False when this JWT did not prove a second factor at sign-in while org policy requires it "
            "(password-only session under mandate). Derived from GET /auth/me using the request token."
        ),
    )
    organization_requires_password_rotation: bool = False
    password_rotation_days: int | None = None
    session_password_change_required: bool = Field(
        default=False,
        description=(
            "True when org password rotation policy requires a new password and this JWT was issued before "
            "the change. Derived from GET /auth/me using the request token."
        ),
    )
    appearance: UserAppearanceOut = Field(default_factory=UserAppearanceOut)
    ui_preferences: UserUiPreferencesOut = Field(default_factory=UserUiPreferencesOut)
    has_signature: bool = False
    signature_original_filename: str | None = None
    signature_scale: int = Field(default=7, ge=1, le=10)


class UserSignatureUpdate(BaseModel):
    signature_scale: int = Field(ge=1, le=10)


class UserUiPreferencesUpdate(BaseModel):
    """Partial update for per-user UI preferences."""

    calendar_view: Literal["dayGridMonth", "timeGridWeek", "timeGridDay", "listYear"] | None = None
    case_calendar_view: Literal["dayGridMonth", "timeGridWeek", "timeGridDay", "listYear"] | None = None
    tasks_menu_layout: Literal["list", "kanban"] | None = None
    case_tasks_layout: Literal["list", "kanban"] | None = None
    tasks_menu_sort_key: Literal["reference", "client", "matter", "task", "date", "assigned", "priority"] | None = None
    tasks_menu_sort_dir: Literal["asc", "desc"] | None = None
    case_tasks_sort_key: Literal["reference", "client", "matter", "task", "date", "assigned", "priority"] | None = None
    case_tasks_sort_dir: Literal["asc", "desc"] | None = None
    main_menu_sort_key: Literal["reference", "client", "matter", "feeEarner", "status", "created"] | None = None
    main_menu_sort_dir: Literal["asc", "desc"] | None = None
    main_menu_search: str | None = Field(default=None, max_length=500)
    main_menu_filter_matter_type: str | None = Field(default=None, max_length=200)
    main_menu_filter_fee_earner_user_id: str | None = Field(default=None, max_length=36)
    main_menu_filter_case_status: Literal["", "open", "closed", "archived", "quote", "quote_closed", "post_completion"] | None = None
    main_menu_filter_matter_types: list[str] | None = None
    main_menu_filter_fee_earner_user_ids: list[str] | None = None
    main_menu_filter_case_statuses: list[Literal["open", "closed", "archived", "quote", "quote_closed", "post_completion"]] | None = None
    tasks_menu_search: str | None = Field(default=None, max_length=500)
    tasks_menu_filter_matter_type: str | None = Field(default=None, max_length=200)
    contacts_search: str | None = Field(default=None, max_length=500)
    contacts_sort_key: Literal["name", "type", "email", "phone"] | None = None
    contacts_sort_dir: Literal["asc", "desc"] | None = None
    calendar_selected_calendar_ids: list[str] | None = None
    main_menu_column_widths: list[int] | None = None
    tasks_menu_column_widths: list[int] | None = None
    contacts_column_widths: list[int] | None = None


class Verify2FASessionResponse(BaseModel):
    """Returned after successful authenticator enrolment: replaces the restricted-session JWT."""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class UserEmailHandlingUpdate(BaseModel):
    """How matter e-mail compose opens: desktop mailto vs Outlook on the web."""

    email_launch_preference: Literal["desktop", "outlook_web"]
    email_outlook_web_url: str | None = Field(default=None, max_length=2000)
    email_desktop_client: Literal["outlook", "other"] | None = None


class LedgerPermissionsOut(BaseModel):
    can_approve_ledger: bool
    can_approve_invoices: bool = False
    accounts_workspace_access: bool = False
    can_post_client: bool = False
    can_post_office: bool = False
    can_post_anticipated: bool = False


class UserCalDAVStatusOut(BaseModel):
    enabled: bool
    caldav_url: str
    caldav_username: str


class UserCalDAVProvisionOut(BaseModel):
    caldav_url: str
    caldav_username: str
    caldav_password: str
    note: str = (
        "Save this password now — it will not be shown again. "
        "Use it as the CalDAV password in your calendar app (not your Canary login)."
    )


class CalendarEventOut(BaseModel):
    id: str
    uid: str
    title: str
    start: str
    end: str
    all_day: bool = False
    description: str | None = None
    calendar_name: str | None = None
    calendar_id: str | None = None
    can_edit: bool = True
    # Canary-only category (not in iCal).
    category_id: uuid.UUID | None = None
    category_name: str | None = None
    category_color: str | None = None
    # Matter-linked row merged into the feed (not from Radicale).
    case_id: uuid.UUID | None = None
    case_event_id: uuid.UUID | None = None
    track_in_calendar: bool | None = None
    matter_template_id: uuid.UUID | None = None
    email_alert_enabled: bool = False


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    start: datetime | date
    end: datetime | date
    all_day: bool = False
    description: str | None = Field(default=None, max_length=20000)
    calendar_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    email_alert: bool = False
    matter_sub_type_event_template_id: uuid.UUID | None = None


class CalendarEventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    start: datetime | date | None = None
    end: datetime | date | None = None
    all_day: bool | None = None
    description: str | None = Field(default=None, max_length=20000)
    category_id: uuid.UUID | None = None
    email_alert: bool | None = None
    matter_sub_type_event_template_id: uuid.UUID | None = None


class CalendarCategoryOut(BaseModel):
    id: uuid.UUID
    calendar_id: uuid.UUID
    name: str
    color: str | None = None


class CalendarCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=20)


class CalendarCategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=20)


class CalendarCategorySyncOut(BaseModel):
    updated: int
    cleared: int


class CalendarOwnerMini(BaseModel):
    id: uuid.UUID
    display_name: str
    email: EmailStr


class UserCalendarOut(BaseModel):
    id: uuid.UUID
    name: str
    radicale_slug: str
    is_public: bool
    access: Literal["owner", "read", "write"]
    source: Literal["owned", "share", "subscription"]
    owner: CalendarOwnerMini


class CalendarShareOut(BaseModel):
    grantee_user_id: uuid.UUID
    grantee_display_name: str
    grantee_email: EmailStr
    can_write: bool


class CalendarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CalendarPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_public: bool | None = None


class CalendarShareCreate(BaseModel):
    grantee_user_id: uuid.UUID
    can_write: bool = False


class CalendarSubscribeIn(BaseModel):
    calendar_id: uuid.UUID


class CalendarDirectoryRow(BaseModel):
    id: uuid.UUID
    name: str
    owner: CalendarOwnerMini
    is_public: bool
    shared_directly: bool
    already_in_my_list: bool
    can_subscribe: bool


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320, description="Staff login id (e-mail or reserved master login).")
    password: str
    totp_code: str | None = None


class Setup2FARequest(BaseModel):
    """Optional password when resuming a pending authenticator setup."""

    password: str | None = None


class Setup2FAResponse(BaseModel):
    secret: str
    otpauth_uri: str


class Verify2FARequest(BaseModel):
    code: str = Field(min_length=4, max_length=12)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class ChangePasswordResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=12)


class AdminSendPasswordResetResponse(BaseModel):
    email_sent: bool
    message: str | None = None


class UserDisable2FARequest(BaseModel):
    password: str
    totp_code: str = Field(min_length=6, max_length=12)


class Cancel2FASetupRequest(BaseModel):
    password: str


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    display_name: str = Field(min_length=1, max_length=200)
    initials: str = Field(min_length=1, max_length=12)
    job_title: str | None = Field(default=None, max_length=300)
    role: UserRole = UserRole.user
    is_active: bool = True
    permission_category_id: uuid.UUID

    @field_validator("initials", mode="after")
    @classmethod
    def _admin_create_initials(cls, v: str) -> str:
        return normalize_initials(v)


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    initials: str | None = Field(default=None, min_length=1, max_length=12)
    job_title: str | None = Field(default=None, max_length=300)
    role: UserRole | None = None
    is_active: bool | None = None
    permission_category_id: uuid.UUID | None = None
    charge_rate_pence_per_hour: int | None = Field(default=None, ge=0)

    @field_validator("initials", mode="after")
    @classmethod
    def _admin_update_initials(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_initials(v)


class AdminUserPublic(UserPublic):
    permission_category_id: uuid.UUID | None = None
    charge_rate_pence_per_hour: int | None = None


class UserPermissionCategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    perm_fee_earner: bool
    perm_post_client: bool
    perm_post_office: bool
    perm_post_anticipated: bool
    perm_approve_payments: bool
    perm_approve_invoices: bool
    perm_admin: bool
    created_at: datetime
    updated_at: datetime
    is_builtin_template: bool = False

    model_config = {"from_attributes": True}


class UserPermissionCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    perm_fee_earner: bool = False
    perm_post_client: bool = False
    perm_post_office: bool = False
    perm_post_anticipated: bool = False
    perm_approve_payments: bool = False
    perm_approve_invoices: bool = False
    perm_admin: bool = False


class UserPermissionCategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    perm_fee_earner: bool | None = None
    perm_post_client: bool | None = None
    perm_post_office: bool | None = None
    perm_post_anticipated: bool | None = None
    perm_approve_payments: bool | None = None
    perm_approve_invoices: bool | None = None
    perm_admin: bool | None = None


class AdminUserSetPassword(BaseModel):
    password: str = Field(min_length=12)


class FirmSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    trading_name: str = ""
    registered_company_name: str | None = None
    addr_line1: str | None = None
    addr_line2: str | None = None
    town_city: str | None = None
    county: str | None = None
    postcode: str | None = None
    letterhead_style: LetterheadStyle = LetterheadStyle.preprinted
    letterhead_original_filename: str | None = None
    quote_letterhead_style: LetterheadStyle = LetterheadStyle.preprinted
    quote_letterhead_original_filename: str | None = None
    portal_logo_configured: bool = False
    portal_logo_original_filename: str | None = None
    mandate_two_factor: bool = False
    mandate_password_rotation: bool = False
    password_rotation_days: int | None = None
    client_bank_account_name: str | None = None
    client_bank_sort_code: str | None = None
    client_bank_account_number_last4: str | None = None
    client_bank_account_number: str | None = None


class MergeCodeCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str
    sort_order: int


class MergeCodeCatalogRowIn(BaseModel):
    code: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=16000)


class MergeCodeCatalogBulkUpdate(BaseModel):
    items: list[MergeCodeCatalogRowIn]


class MergeCodeCatalogImportResult(BaseModel):
    updated: int
    skipped_unknown: int


class FirmSettingsUpdate(BaseModel):
    trading_name: str | None = Field(default=None, max_length=300)
    registered_company_name: str | None = Field(default=None, max_length=400)
    addr_line1: str | None = Field(default=None, max_length=300)
    addr_line2: str | None = Field(default=None, max_length=300)
    town_city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    letterhead_style: LetterheadStyle | None = None
    quote_letterhead_style: LetterheadStyle | None = None
    mandate_two_factor: bool | None = None
    mandate_password_rotation: bool | None = None
    password_rotation_days: int | None = Field(default=None, ge=1, le=3650)
    client_bank_account_name: str | None = Field(default=None, max_length=200)
    client_bank_sort_code: str | None = Field(default=None, max_length=16)
    client_bank_account_number_last4: str | None = Field(default=None, max_length=4)
    client_bank_account_number: str | None = Field(default=None, max_length=20)


class MatterHeadTypeVisibilityUpdate(BaseModel):
    is_hidden: bool


class MatterSubTypeMenuOut(BaseModel):
    id: uuid.UUID
    name: str


class MatterSubTypeMenuCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MatterSubTypeMenuUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MatterSubTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str | None
    menus: list[MatterSubTypeMenuOut] = []


class MatterHeadTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    is_hidden: bool = False
    sub_types: list[MatterSubTypeOut] = []


class MatterSubTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MatterSubTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prefix: str | None = None


class CaseCreate(BaseModel):
    matter_description: str = Field(min_length=1, max_length=300)
    status: CaseStatus = CaseStatus.open
    practice_area: str | None = Field(default=None, max_length=200)
    matter_sub_type_id: uuid.UUID
    fee_earner_user_id: uuid.UUID
    source_id: uuid.UUID | None = None
    source_name: str | None = Field(default=None, max_length=200)
    portal_enabled: bool = False

    @field_validator("status")
    @classmethod
    def new_matter_status_open_or_quote_only(cls, v: CaseStatus) -> CaseStatus:
        if v not in (CaseStatus.open, CaseStatus.quote):
            raise ValueError("New matters may only be created as Active (open) or Quote.")
        return v


class CaseUpdate(BaseModel):
    matter_description: str | None = Field(default=None, min_length=1, max_length=300)
    fee_earner_user_id: uuid.UUID | None = None
    status: CaseStatus | None = None
    practice_area: str | None = Field(default=None, max_length=200)
    matter_sub_type_id: uuid.UUID | None = None
    matter_head_type_id: uuid.UUID | None = None
    is_locked: bool | None = None
    lock_mode: CaseLockMode | None = None
    source_id: uuid.UUID | None = None
    source_name: str | None = Field(default=None, max_length=200)
    portal_enabled: bool | None = None


class MatterMenuItemOut(BaseModel):
    id: uuid.UUID
    name: str


class CaseOut(BaseModel):
    id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str
    fee_earner_user_id: uuid.UUID
    status: CaseStatus
    practice_area: str | None
    matter_sub_type_id: uuid.UUID | None
    matter_head_type_id: uuid.UUID | None
    matter_sub_type_name: str | None
    matter_head_type_name: str | None
    matter_menus: list[MatterMenuItemOut] = Field(default_factory=list)
    source_id: uuid.UUID | None = None
    source_name: str | None = None
    created_by: uuid.UUID
    is_locked: bool
    lock_mode: CaseLockMode
    portal_enabled: bool = False
    created_at: datetime
    updated_at: datetime


class MatterContactTypeOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    sort_order: int
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class CaseSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    sort_order: int
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class CaseSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CaseSourceAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None


class MatterContactTypeAdminCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    sort_order: int = 0


class MatterContactTypeAdminUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None


class CasePropertyUK(BaseModel):
    line1: str | None = Field(default=None, max_length=300)
    line2: str | None = Field(default=None, max_length=300)
    town: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=200)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)


class CasePropertyPayload(BaseModel):
    """Stored in case_property_details.payload."""

    is_non_postal: bool = False
    uk: CasePropertyUK = Field(default_factory=CasePropertyUK)
    free_lines: list[str] = Field(default_factory=lambda: ["", "", "", "", "", ""])
    title_numbers: list[str] = Field(default_factory=list)
    tenure: Literal["freehold", "leasehold", "commonhold"] | None = None
    existing_lender_case_contact_id: uuid.UUID | None = None
    charge_date: str | None = Field(default=None, max_length=10)


class CasePropertyDetailsOut(BaseModel):
    has_details: bool
    payload: CasePropertyPayload
    updated_at: datetime | None = None


class PrecedentCategoryOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class PrecedentCategoryFlatOut(PrecedentCategoryOut):
    """Admin list: categories with sub-type label for grouping in the UI."""

    matter_sub_type_name: str


class PrecedentCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0


class PrecedentCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None


class PrecedentOut(BaseModel):
    id: uuid.UUID
    name: str
    reference: str
    kind: PrecedentKind
    original_filename: str
    mime_type: str
    category_id: uuid.UUID | None = None
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    category_name: str | None = None
    matter_head_type_name: str | None = None
    matter_sub_type_name: str | None = None
    scope_summary: str = ""
    created_at: datetime


class PrecedentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: uuid.UUID | None = None
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None


class FeeScaleOut(BaseModel):
    id: uuid.UUID
    name: str
    reference: str
    vat_rate_bps: int = 2000
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    matter_head_type_name: str | None = None
    matter_sub_type_name: str | None = None
    scope_summary: str | None = None
    is_favorited: bool = False
    created_at: datetime
    updated_at: datetime


class FeeScaleFavoriteUpdate(BaseModel):
    favorited: bool


class FeeScaleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    reference: str = Field(min_length=1, max_length=200)
    vat_rate_bps: int = Field(default=2000, ge=0, le=10000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None


class FeeScaleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    vat_rate_bps: int | None = Field(default=None, ge=0, le=10000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None


class FeeScaleLineOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    line_kind: Literal["section_header", "item", "vat", "subtotal", "total"]
    amount_kind: Literal["fixed", "editable", "band"] | None = None
    default_amount_pence: int | None = None
    band_set_id: uuid.UUID | None = None
    vat_treatment: Literal["included", "plus_vat"] = "included"
    sort_order: int


class FeeScaleCategoryOut(BaseModel):
    id: uuid.UUID
    fee_scale_id: uuid.UUID
    name: str
    sort_order: int
    lines: list[FeeScaleLineOut] = Field(default_factory=list)


class FeeScaleBandRowOut(BaseModel):
    id: uuid.UUID
    band_set_id: uuid.UUID
    min_value_pence: int
    max_value_pence: int | None = None
    amount_pence: int
    sort_order: int


class FeeScaleBandSetOut(BaseModel):
    id: uuid.UUID
    fee_scale_id: uuid.UUID
    name: str
    sort_order: int
    rows: list[FeeScaleBandRowOut] = Field(default_factory=list)


class FeeScaleDetailOut(FeeScaleOut):
    categories: list[FeeScaleCategoryOut] = Field(default_factory=list)
    band_sets: list[FeeScaleBandSetOut] = Field(default_factory=list)


class FeeScaleCategoryCreate(BaseModel):
    fee_scale_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0


class FeeScaleCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None


class FeeScaleLineCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=300)
    line_kind: Literal["section_header", "item", "vat", "subtotal", "total"]
    amount_kind: Literal["fixed", "editable", "band"] | None = None
    default_amount_pence: int | None = None
    band_set_id: uuid.UUID | None = None
    vat_treatment: Literal["included", "plus_vat"] = "included"
    sort_order: int = 0


class FeeScaleLineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    line_kind: Literal["section_header", "item", "vat", "subtotal", "total"] | None = None
    amount_kind: Literal["fixed", "editable", "band"] | None = None
    default_amount_pence: int | None = None
    band_set_id: uuid.UUID | None = None
    vat_treatment: Literal["included", "plus_vat"] | None = None
    sort_order: int | None = None


class FeeScaleBandSetCreate(BaseModel):
    fee_scale_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0


class FeeScaleBandSetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None


class FeeScaleBandRowCreate(BaseModel):
    band_set_id: uuid.UUID
    min_value_pence: int = Field(ge=0)
    max_value_pence: int | None = Field(default=None, ge=0)
    amount_pence: int = Field(ge=0)
    sort_order: int = 0


class FeeScaleBandRowUpdate(BaseModel):
    min_value_pence: int | None = Field(default=None, ge=0)
    max_value_pence: int | None = None
    amount_pence: int | None = Field(default=None, ge=0)
    sort_order: int | None = None


class QuotePreviewLineOut(BaseModel):
    key: str | None = None
    line_id: uuid.UUID | None = None
    name: str
    line_kind: str
    amount_pence: int | None = None
    amount_display: str | None = None
    editable: bool = False
    is_bold: bool = False
    vat_pence: int | None = None
    vat_treatment: Literal["included", "plus_vat"] | None = None
    amount_kind: str | None = None
    band_set_id: uuid.UUID | None = None
    sort_order: int = 0


class QuotePreviewCategoryOut(BaseModel):
    key: str
    category_id: uuid.UUID | None = None
    name: str
    sort_order: int
    lines: list[QuotePreviewLineOut]


class QuotePreviewOut(BaseModel):
    fee_scale_id: uuid.UUID
    property_value_pence: int | None = None
    needs_property_value: bool = False
    lines: list[QuotePreviewLineOut]
    categories: list[QuotePreviewCategoryOut] = Field(default_factory=list)


class QuoteDraftLineIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    line_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=512)
    line_kind: str
    amount_kind: str | None = None
    amount_pence: int | None = Field(default=None, ge=0)
    vat_treatment: Literal["included", "plus_vat"] = "included"
    band_set_id: uuid.UUID | None = None
    sort_order: int = 0


class QuoteDraftCategoryIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    category_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=256)
    sort_order: int = 0
    lines: list[QuoteDraftLineIn] = Field(default_factory=list)


class QuotePreviewIn(BaseModel):
    property_value_pence: int | None = Field(default=None, ge=0)
    line_overrides: dict[str, int] = Field(default_factory=dict)
    amount_overrides: dict[str, int] = Field(default_factory=dict)
    draft: list[QuoteDraftCategoryIn] | None = None


class ComposeQuoteLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    line_kind: str
    amount_pence: int | None = Field(default=None, ge=0)
    vat_pence: int | None = Field(default=None, ge=0)
    is_bold: bool = False


class ComposeQuoteIn(BaseModel):
    original_filename: str = Field(min_length=1, max_length=512)
    folder: str = ""
    fee_scale_id: uuid.UUID | None = None
    case_contact_id: uuid.UUID | None = None
    global_contact_id: uuid.UUID | None = None
    precedent_merge_all_clients: bool = False
    property_value_pence: int | None = Field(default=None, ge=0)
    line_overrides: dict[str, int] = Field(default_factory=dict)
    amount_overrides: dict[str, int] = Field(default_factory=dict)
    draft: list[QuoteDraftCategoryIn] | None = None
    quote_lines: list[ComposeQuoteLineIn] | None = None


class ComposeOfficeDocumentIn(BaseModel):
    original_filename: str = Field(min_length=1, max_length=512)
    folder: str = ""
    precedent_id: uuid.UUID | None = None
    # When ``precedent_id`` is omitted: ``letter`` resolves to the reserved ``BLANK_LETTER`` precedent;
    # ``document`` keeps a minimal empty .docx. If omitted, the server infers from ``original_filename``
    # (``Letter — …`` vs ``Document — …`` as produced by the web UI).
    compose_office_role: Literal["letter", "document"] | None = None
    # Contact for precedent code merge; one of these may be supplied
    case_contact_id: uuid.UUID | None = None   # CaseContact row id
    global_contact_id: uuid.UUID | None = None  # global Contact row id
    # When True, fill [TITLE]…[TRADING_NAME_4] from up to four Client matter contacts (by date added).
    # When False and case_contact_id is a Client, only that client’s slot is filled (see docx_util.build_merge_fields).
    # [CONTACT_*] codes always reflect the contact chosen in compose when one is supplied, including alongside merge-all.
    precedent_merge_all_clients: bool = False


class CaseEmailDraftM365In(BaseModel):
    """Create an Outlook draft via Microsoft Graph (same merge inputs as compose-office, plus case file attachments)."""

    folder: str = ""
    precedent_id: uuid.UUID | None = None
    case_contact_id: uuid.UUID | None = None
    global_contact_id: uuid.UUID | None = None
    precedent_merge_all_clients: bool = False
    compose_office_role: Literal["letter", "document"] | None = None
    attachment_file_ids: list[uuid.UUID] = Field(default_factory=list)


class CaseEmailDraftM365AttachmentOut(BaseModel):
    file_id: uuid.UUID
    filename: str


class CaseEmailDraftM365Out(BaseModel):
    to: str = ""
    subject: str = ""
    body: str = ""
    open_url: str
    """OWA compose deeplink for the Graph draft (or prefill compose when there are no attachments)."""
    graph_message_id: str | None = None
    draft_compose_web_link: str | None = None
    """Graph draft in Drafts (attachments on message; may open as preview until Edit)."""
    compose_prefill_url: str | None = None
    attachment_count: int = 0
    compose_handoff_token: str | None = None
    attachment_files: list[CaseEmailDraftM365AttachmentOut] = Field(default_factory=list)


class CaseEmailMailtoOut(BaseModel):
    to: str
    subject: str
    body: str
    attachment_count: int
    note: str = (
        "Standard mailto links cannot attach case files — add attachments manually in your mail program."
    )


class CaseEmailComposeHandoffOut(BaseModel):
    """JWT handoff for Thunderbird (or other mail clients) to open compose with merge + attachments."""

    handoff_token: str
    case_id: uuid.UUID
    expires_in_seconds: int
    thunderbird_hint: str = (
        "In Thunderbird, open Canary → Compose from matter (or paste the handoff if prompted). "
        "The compose window will include the merged body and case attachments."
    )


class MailPluginComposeAttachmentOut(BaseModel):
    file_id: uuid.UUID
    filename: str
    mime_type: str
    content_base64: str


class MailPluginComposeHandoffOut(BaseModel):
    case_id: uuid.UUID
    to: str
    subject: str
    body: str
    attachments: list[MailPluginComposeAttachmentOut] = Field(default_factory=list)


class EmailIntegrationSettingsOut(BaseModel):
    integration_mode: Literal["mailto", "microsoft_graph"]
    graph_tenant_id: str | None
    graph_client_id: str | None
    graph_client_secret_configured: bool
    outlook_web_mail_base: str | None
    alerts_enabled: bool
    alert_transport: Literal["auto", "graph", "smtp"]
    graph_send_mailbox: str | None
    graph_send_from_name: str | None
    graph_alert_ready: bool
    smtp_alert_ready: bool
    effective_alert_transport: Literal["graph", "smtp"] | None


class EmailIntegrationSettingsUpdate(BaseModel):
    integration_mode: Literal["mailto", "microsoft_graph"] | None = None
    graph_tenant_id: str | None = Field(default=None, max_length=2000)
    graph_client_id: str | None = Field(default=None, max_length=2000)
    graph_client_secret: str | None = Field(default=None, max_length=2000)
    outlook_web_mail_base: str | None = Field(default=None, max_length=2000)
    alerts_enabled: bool | None = None
    alert_transport: Literal["auto", "graph", "smtp"] | None = None
    graph_send_mailbox: str | None = Field(default=None, max_length=320)
    graph_send_from_name: str | None = Field(default=None, max_length=200)


class FirmAlertTestIn(BaseModel):
    to_email: EmailStr


class SmtpNotificationSettingsOut(BaseModel):
    enabled: bool
    host: str | None
    port: int
    use_tls: bool
    username: str | None
    password_configured: bool
    from_email: str | None
    from_name: str | None


class SmtpNotificationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    host: str | None = Field(default=None, max_length=300)
    port: int | None = Field(default=None, ge=1, le=65535)
    use_tls: bool | None = None
    username: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, max_length=500)
    from_email: str | None = Field(default=None, max_length=320)
    from_name: str | None = Field(default=None, max_length=200)


class SmtpNotificationTestIn(BaseModel):
    to_email: EmailStr


class AdminDeployStatusOut(BaseModel):
    """Deploy/update capabilities exposed to admins (no secrets)."""

    configured: bool
    compose_update_enabled: bool = False
    compose_git_reset_enabled: bool = False
    compose_git_ref: str = "main"


class AdminDeployTriggerIn(BaseModel):
    """Trigger a Docker Compose pull/build/up on the host (self-host)."""

    method: Literal["auto", "compose"] = Field(
        default="auto",
        description="Both values run the Compose update path; ``auto`` is kept for older clients.",
    )
    git_strategy: Literal["ff-only", "reset"] = Field(
        default="ff-only",
        description=(
            "``ff-only``: ``git pull --ff-only`` when ``CANARY_COMPOSE_GIT_PULL`` is set. "
            "``reset``: ``git fetch`` + ``reset --hard`` to ``CANARY_GITHUB_DEPLOY_REF`` "
            "(requires ``CANARY_COMPOSE_GIT_RESET_ENABLED``)."
        ),
    )

    model_config = {"extra": "forbid"}


class AdminDeployTriggerOut(BaseModel):
    ok: bool = True
    message: str
    async_mode: bool = False
    job_id: str | None = None


class AdminDeployComposeJobOut(BaseModel):
    """Background compose job status (in-process; single worker recommended)."""

    status: Literal["idle", "running", "succeeded", "failed"]
    job_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    error_detail: str | None = None
    log_excerpt: str | None = None
    journal_lines: list[str] = Field(default_factory=list)
    progress_phase: Literal["git", "build", "up"] | None = None
    elapsed_seconds: float | None = None


class AdminDeployUpdateCheckOut(BaseModel):
    """Admin-only: compare running image commit to GitHub default branch + optional release notes."""

    github_repo_configured: bool
    deploy_trigger_configured: bool = False
    compose_update_enabled: bool = False
    compose_git_reset_enabled: bool = False
    compose_git_ref: str = "main"
    prompt_enabled: bool
    current_commit: str
    current_commit_short: str
    remote_ref: str
    remote_commit: str
    remote_commit_short: str
    update_available: bool
    build_commit_unknown: bool
    compare_html_url: str | None = None
    latest_release_tag: str | None = None
    latest_release_name: str | None = None
    latest_release_body: str | None = None
    commit_messages: list[str] = []
    note: str | None = None


class AdminStorageCategoryOut(BaseModel):
    category: str
    label: str
    bytes_used: int = Field(ge=0)
    file_count: int = Field(ge=0)


class AdminStorageDeploymentComponentOut(BaseModel):
    key: str
    label: str
    bytes_used: int = Field(ge=0)
    detected: bool


class AdminStorageOut(BaseModel):
    tracked_total_bytes: int = Field(ge=0)
    files_on_disk_bytes: int = Field(ge=0)
    compose_mount_bytes: int = Field(ge=0)
    application_checkout_bytes: int = Field(ge=0)
    database_bytes: int | None = Field(default=None, ge=0)
    database_logical_bytes: int | None = Field(default=None, ge=0)
    calendars_bytes: int | None = Field(default=None, ge=0)
    deployment_total_bytes: int = Field(ge=0)
    docker_detected: bool = False
    docker_images_bytes: int = Field(default=0, ge=0)
    docker_container_writable_bytes: int = Field(default=0, ge=0)
    docker_dangling_images_bytes: int = Field(default=0, ge=0)
    docker_build_cache_bytes: int | None = Field(default=None, ge=0)
    deployment_active_bytes: int = Field(default=0, ge=0)
    deployment_artifacts_bytes: int = Field(default=0, ge=0)
    measurement_note: str | None = None
    deployment_components: list[AdminStorageDeploymentComponentOut]
    categories: list[AdminStorageCategoryOut]
    storage_limit_bytes: int | None = None
    files_root: str
    host_disk_detected: bool
    host_disk_total_bytes: int | None = Field(default=None, ge=0)
    host_disk_used_bytes: int | None = Field(default=None, ge=0)
    host_disk_free_bytes: int | None = Field(default=None, ge=0)


class AdminStorageSettingsPatch(BaseModel):
    storage_limit_bytes: int | None = Field(
        default=None,
        ge=1,
        le=10_000_000_000_000_000,
        description="Firm-wide storage quota for tracked files; null clears the limit.",
    )

    model_config = {"extra": "forbid"}


class ContactCreate(BaseModel):
    type: ContactType
    name: str = Field(min_length=1, max_length=300)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    # Person name fields
    title: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=150)
    middle_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
    # Organisation fields
    company_name: str | None = Field(default=None, max_length=300)
    trading_name: str | None = Field(default=None, max_length=300)
    # Address
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _organisation_requires_trading_name(self) -> ContactCreate:
        if self.type == ContactType.organisation and not (self.trading_name or "").strip():
            raise ValueError("Trading name is required for organisation contacts.")
        return self


class ContactUpdate(BaseModel):
    """PATCH `/contacts/{id}` — partial body; organisation trading-name rules enforced after merge in the router."""

    type: ContactType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=150)
    middle_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
    company_name: str | None = Field(default=None, max_length=300)
    trading_name: str | None = Field(default=None, max_length=300)
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)


class ContactOut(BaseModel):
    id: uuid.UUID
    type: ContactType
    name: str
    email: EmailStr | None
    phone: str | None
    title: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    trading_name: str | None = None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    county: str | None = None
    postcode: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime


class CaseContactCreateFromGlobal(BaseModel):
    contact_id: uuid.UUID
    matter_contact_type: str = Field(min_length=1, max_length=200)
    matter_contact_reference: str | None = Field(default=None, max_length=500)
    lawyer_client_ids: list[uuid.UUID] | None = None
    letter_salutation: str | None = Field(default=None, max_length=64)
    letter_salutation_custom: str | None = Field(default=None, max_length=500)


class CaseContactUpdate(BaseModel):
    type: ContactType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=150)
    middle_name: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=150)
    company_name: str | None = Field(default=None, max_length=300)
    trading_name: str | None = Field(default=None, max_length=300)
    address_line1: str | None = Field(default=None, max_length=300)
    address_line2: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=200)
    county: str | None = Field(default=None, max_length=150)
    postcode: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    matter_contact_type: str | None = Field(default=None, min_length=1, max_length=200)
    matter_contact_reference: str | None = Field(default=None, max_length=500)
    lawyer_client_ids: list[uuid.UUID] | None = None
    letter_salutation: str | None = Field(default=None, max_length=64)
    letter_salutation_custom: str | None = Field(default=None, max_length=500)
    push_to_global: bool = False


class CaseContactOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    contact_id: uuid.UUID | None
    is_linked_to_master: bool
    type: ContactType
    name: str
    email: EmailStr | None
    phone: str | None
    title: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    trading_name: str | None = None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    county: str | None = None
    postcode: str | None
    country: str | None
    matter_contact_type: str | None = None
    matter_contact_reference: str | None = None
    lawyer_client_ids: list[uuid.UUID] = Field(default_factory=list)
    letter_salutation: str | None = None
    letter_salutation_custom: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("lawyer_client_ids", mode="before")
    @classmethod
    def _lawyer_ids_from_json(cls, v: object) -> list[uuid.UUID]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: list[uuid.UUID] = []
        for x in v:
            out.append(uuid.UUID(str(x)))
        return out


class CaseNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class CaseNoteUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class CaseNoteOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime


class MatterSubTypeStandardTaskCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    sort_order: int = 0


class MatterSubTypeStandardTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    sort_order: int | None = None


class MatterSubTypeStandardTaskOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID | None
    title: str
    sort_order: int
    is_system: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


CaseTaskPriority = Literal["low", "normal", "high"]


class CaseTaskCreate(BaseModel):
    """Custom task: set title. Standard task: set standard_task_id (title from template unless ``title`` overrides)."""

    title: str | None = Field(default=None, max_length=300)
    standard_task_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=20000)
    due_at: datetime | None = None
    assigned_to_user_id: uuid.UUID | None = None
    priority: CaseTaskPriority = "normal"
    is_private: bool = False

    @model_validator(mode="after")
    def title_or_standard(self) -> CaseTaskCreate:
        if self.standard_task_id is None and (self.title is None or not str(self.title).strip()):
            raise ValueError("title is required when standard_task_id is not set")
        return self


class CaseTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    status: CaseTaskStatus | None = None
    due_at: datetime | None = None
    assigned_to_user_id: uuid.UUID | None = None
    priority: CaseTaskPriority | None = None
    is_private: bool | None = None
    standard_task_id: uuid.UUID | None = None


class CaseTaskOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    created_by_user_id: uuid.UUID
    title: str
    description: str | None
    status: CaseTaskStatus
    due_at: datetime | None
    standard_task_id: uuid.UUID | None = None
    assigned_to_user_id: uuid.UUID | None = None
    assigned_display_name: str | None = None
    priority: CaseTaskPriority = "normal"
    case_event_id: uuid.UUID | None = None
    is_private: bool = False
    created_at: datetime
    updated_at: datetime


class CaseTimeEntryCreate(BaseModel):
    work_date: date
    duration_minutes: int = Field(ge=6)
    description: str = Field(min_length=1, max_length=4000)
    user_id: uuid.UUID | None = None
    non_billable: bool = False

    model_config = {"extra": "forbid"}


class CaseTimeEntryUpdate(BaseModel):
    work_date: date | None = None
    duration_minutes: int | None = Field(default=None, ge=6)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    user_id: uuid.UUID | None = None
    non_billable: bool | None = None

    model_config = {"extra": "forbid"}


class CaseTimeEntryOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    user_id: uuid.UUID
    user_display_name: str
    created_by_user_id: uuid.UUID
    work_date: date
    duration_minutes: int
    duration_tenths: int
    description: str
    status: Literal["unbilled", "billed", "written_off"]
    invoice_line_id: uuid.UUID | None = None
    non_billable: bool = False
    charge_rate_pence_per_hour: int | None = None
    value_pence: int | None = None
    created_at: datetime
    updated_at: datetime


class TaskMenuRowOut(BaseModel):
    """Case tasks for the global Tasks menu (one row per task)."""

    id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None
    matter_description: str | None
    matter_type_label: str
    task_title: str
    date: datetime
    assigned_display_name: str | None = None
    priority: CaseTaskPriority = "normal"
    status: CaseTaskStatus
    is_private: bool = False
    standard_task_id: uuid.UUID | None = None
    """Resolved template title for Kanban columns (standard tasks)."""
    standard_task_category_title: str | None = None


class FilePinUpdate(BaseModel):
    is_pinned: bool


class OutlookOpenHintsOut(BaseModel):
    """Graph / OWA pointers for opening a filed message in Outlook on the web or desktop."""

    outlook_graph_message_id: str | None = None
    outlook_web_link: str | None = None
    # Preferred one-click OWA read URL (built from item id + user/org mail base).
    owa_read_url: str | None = None
    open_in_owa_supported: bool = False


class OutlookPluginLinkedCaseResolveIn(BaseModel):
    outlook_item_id: str | None = None
    internet_message_id: str | None = None
    conversation_id: str | None = None
    source_imap_mbox: str | None = None
    source_imap_uid: str | None = None


class OutlookPluginPendingSendPutIn(BaseModel):
    """Remember a matter for the next message sent from Outlook with the add-in signed in."""

    case_id: uuid.UUID
    source_file_id: uuid.UUID | None = None
    ttl_seconds: int | None = 86400


class OutlookPluginPendingSendOut(BaseModel):
    active: bool
    case_id: uuid.UUID | None = None
    source_file_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class OutlookPluginPendingComposeHandoffPutIn(BaseModel):
    """Queue a compose handoff for the signed-in user's Outlook add-in to claim and open."""

    handoff_token: str = Field(min_length=10)
    ttl_seconds: int | None = 3600


class OutlookPluginPendingComposeHandoffOut(BaseModel):
    active: bool
    handoff_token: str | None = None
    case_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class OutlookPluginLinkedCaseOut(BaseModel):
    id: uuid.UUID
    case_number: str
    client_name: str | None = None
    matter_description: str


class OutlookPluginLinkedCaseResolveOut(BaseModel):
    linked_case: OutlookPluginLinkedCaseOut | None = None


class MailPluginMessageContextOut(BaseModel):
    """Matter + parent e-mail file for a message already filed in Canary (Thunderbird reply prefill)."""

    found: bool = False
    case_id: uuid.UUID | None = None
    file_id: uuid.UUID | None = None
    folder_path: str = ""
    case_number: str | None = None
    client_name: str | None = None
    matter_description: str | None = None


class OutlookPluginEnsureMasterCategoryIn(BaseModel):
    """Mailbox UPN/SMTP for the signed-in Outlook session (must match Canary user email)."""

    mailbox: str


class OutlookPluginEnsureMasterCategoryOut(BaseModel):
    ok: bool
    status: str
    detail: str | None = None


class OutlookPluginGraphTagCategoryIn(BaseModel):
    """
    ``rest_item_id``: prefer ``mailbox.convertToRestId(item.itemId, v2.0)`` for Graph;
    raw ``itemId`` is often EWS-shaped and breaks the Graph URL if unconverted.
    ``internet_message_id``: optional RFC5322 Message-ID for ``$filter`` fallback when GET by id fails.
    """

    mailbox: str
    rest_item_id: str
    internet_message_id: str | None = None


class OutlookPluginGraphTagCategoryOut(BaseModel):
    ok: bool
    status: str
    detail: str | None = None


class OutlookPluginSendCaptureLogIn(BaseModel):
    """Best-effort diagnostic from OnMessageSend (Classic Outlook send filing)."""

    step: str = Field(max_length=64)
    detail: str | None = Field(default=None, max_length=2000)
    case_id: str | None = Field(default=None, max_length=64)


class OutlookPluginSendCaptureLogOut(BaseModel):
    ok: bool = True


class CaseFolderCreate(BaseModel):
    # Relative folder path inside the case ("" == root).
    # Example: "Contracts" or "Contracts/2019"
    folder_path: str


class CaseFolderRenameUpdate(BaseModel):
    old_folder_path: str
    new_folder_path: str


class CaseFolderDeleteUpdate(BaseModel):
    folder_path: str


class CaseFolderMoveUpdate(BaseModel):
    old_folder_path: str
    new_parent_path: str


class CaseFileRenameUpdate(BaseModel):
    original_filename: str = Field(min_length=1, max_length=512)


class CommentFileUpdate(BaseModel):
    text: str = Field(min_length=0, max_length=500_000)


class CaseFileMoveUpdate(BaseModel):
    """Target folder path inside the case (empty string = root)."""

    folder_path: str = ""


class CasePortalFolderAccessGrantOut(BaseModel):
    folder_path: str
    contact_id: uuid.UUID
    contact_name: str


class CasePortalFolderShareContactOut(BaseModel):
    case_contact_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    has_grant: bool
    grant_id: uuid.UUID | None


class FileDesktopCheckoutOut(BaseModel):
    """WebDAV URLs for ONLYOFFICE Desktop (or any WebDAV client). Treat `token` as a password."""

    token: str
    webdav_folder_url: str
    webdav_file_url: str
    filename: str
    expires_at: datetime
    instructions: str
    onlyoffice_cli_hint: str = Field(
        description=(
            "Always empty: ONLYOFFICE Desktop does not open http(s) WebDAV URLs from the CLI (args are local paths only). "
            "Use in-browser ONLYOFFICE or a WebDAV mount."
        ),
    )


class FileEditSessionStatusOut(BaseModel):
    active: bool
    expires_at: datetime | None = None
    webdav_file_url: str | None = None


class OoPersistDownloadIn(BaseModel):
    """ONLYOFFICE ``downloadAs`` export URL for persisting edits to Canary storage."""

    browser_url: str = Field(..., min_length=8, max_length=8000)


class OoExportPdfIn(BaseModel):
    """ONLYOFFICE ``downloadAs('pdf')`` URL for saving a new PDF alongside the source document."""

    browser_url: str = Field(..., min_length=8, max_length=8000)
    filename: str | None = Field(default=None, max_length=512)


class OoExportPdfOut(BaseModel):
    file_id: uuid.UUID
    original_filename: str


class OnlyofficeEditorConfigOut(BaseModel):
    """JWT + plaintext fields for DocsAPI.DocEditor.

    ONLYOFFICE requires the plain config fields (document, editorConfig) to be passed to
    DocsAPI.DocEditor alongside the JWT token. The JWT is a signature of those fields, not
    a replacement — without document.url in the plain config the editor creates a blank iframe.
    """

    document_server_url: str
    token: str
    document_type: str
    # Plain (unsigned) fields that must be passed directly to DocsAPI.DocEditor alongside the JWT.
    document: dict
    editor_config: dict
    # Case compose-office: file stays hidden until Save; editor should treat as needing explicit save/close flow.
    oo_compose_pending: bool = False
    folder_path: str = ""
    original_filename: str = ""


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

class LedgerPostCreate(BaseModel):
    """
    Body for POST /cases/{id}/ledger/post.

    A single posting records one transaction that affects one or both accounts.
    SAR-typical use cases:
      - client receipt  : debit client, credit client  (money in to client account)
      - bill payment    : debit client, credit office   (transfer to office on bill)
      - office disbursement: debit office, credit office (e.g. search fee)
    """

    description: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    contact_label: str | None = Field(default=None, max_length=300)
    case_contact_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    amount_pence: int = Field(gt=0, description="Amount in pence (integer)")
    # Which account(s) to affect and in which direction.
    # At least one leg is required; both may be supplied.
    client_direction: Literal["debit", "credit"] | None = None
    office_direction: Literal["debit", "credit"] | None = None
    anticipated: bool = False
    anticipated_for_date: date | None = None

    @model_validator(mode="after")
    def anticipated_date_required(self) -> LedgerPostCreate:
        if self.anticipated and self.anticipated_for_date is None:
            raise ValueError("anticipated_for_date is required when anticipated is true")
        return self

    model_config = {"extra": "forbid"}


class LedgerPairUpdate(BaseModel):
    """Edit an unapproved or anticipated posting before approval."""

    amount_pence: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=200)
    anticipated_for_date: date | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def at_least_one_field(self) -> LedgerPairUpdate:
        if (
            self.amount_pence is None
            and self.description is None
            and self.reference is None
            and self.anticipated_for_date is None
        ):
            raise ValueError("At least one field is required.")
        return self


class RejectCommentIn(BaseModel):
    """Optional comment when rejecting an anticipated payment or pending invoice."""

    comment: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class LedgerEntryOut(BaseModel):
    id: uuid.UUID
    pair_id: uuid.UUID
    account_type: Literal["client", "office"]
    direction: Literal["debit", "credit"]
    amount_pence: int
    description: str
    reference: str | None
    contact_label: str | None = None
    case_contact_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    posted_by_user_id: uuid.UUID | None
    posted_at: datetime
    is_approved: bool
    is_anticipated: bool = False
    anticipated_for_date: date | None = None

    model_config = {"from_attributes": True}


class LedgerAccountSummary(BaseModel):
    account_type: Literal["client", "office"]
    balance_pence: int  # positive = net credit; negative = net debit


class LedgerOut(BaseModel):
    entries: list[LedgerEntryOut]
    client: LedgerAccountSummary
    office: LedgerAccountSummary


class CaseInvoiceLineCreate(BaseModel):
    line_type: Literal["fee", "disbursement", "vat"]
    description: str = Field(min_length=1, max_length=500)
    amount_pence: int = Field(gt=0)
    tax_pence: int = Field(default=0, ge=0)
    credit_user_id: uuid.UUID | None = None


class CaseInvoiceCreate(BaseModel):
    credit_user_id: uuid.UUID
    payee_name: str | None = Field(default=None, max_length=500)
    contact_id: uuid.UUID | None = None
    lines: list[CaseInvoiceLineCreate] = Field(default_factory=list)
    time_entry_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_lines_or_time(self) -> CaseInvoiceCreate:
        if not self.lines and not self.time_entry_ids:
            raise ValueError("At least one invoice line or time entry is required.")
        return self

    model_config = {"extra": "forbid"}


class CaseInvoiceLineOut(BaseModel):
    id: uuid.UUID
    line_type: str
    description: str
    amount_pence: int
    tax_pence: int
    credit_user_id: uuid.UUID | None


class CaseInvoiceOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    invoice_number: str
    status: str
    total_pence: int
    payee_name: str | None
    credit_user_id: uuid.UUID | None = None
    credit_user_display_name: str | None = None
    contact_id: uuid.UUID | None
    ledger_pair_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    voided_at: datetime | None
    created_at: datetime
    document_file_id: uuid.UUID | None = None
    lines: list[CaseInvoiceLineOut]


class CaseInvoicesOut(BaseModel):
    case_id: uuid.UUID
    invoices: list[CaseInvoiceOut]


class BillingSettingsOut(BaseModel):
    default_vat_percent: float


class BillingSettingsUpdate(BaseModel):
    default_vat_percent: float = Field(ge=0, le=100)

    model_config = {"extra": "forbid"}


class BillingLineTemplateOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    line_kind: Literal["fee", "disbursement"]
    label: str
    default_amount_pence: int
    sort_order: int


class BillingLineTemplateCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    line_kind: Literal["fee", "disbursement"]
    label: str = Field(min_length=1, max_length=200)
    default_amount_pence: int = Field(default=0, ge=0)
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class BillingLineTemplateUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    default_amount_pence: int | None = Field(default=None, ge=0)
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class InvoiceBillingDefaultsUser(BaseModel):
    id: str
    email: str
    display_name: str


class InvoiceBillingDefaultsOut(BaseModel):
    default_vat_percent: float
    fee_earner_user_id: uuid.UUID | None = None
    fee_templates: list[BillingLineTemplateOut]
    disbursement_templates: list[BillingLineTemplateOut]
    users: list[InvoiceBillingDefaultsUser]


# ---------------------------------------------------------------------------
# Finance templates (admin)
# ---------------------------------------------------------------------------

class FinanceItemTemplateCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    direction: Literal["debit", "credit"]
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class FinanceItemTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    direction: Literal["debit", "credit"] | None = None
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class FinanceItemTemplateOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    direction: Literal["debit", "credit"]
    sort_order: int


class FinanceCategoryTemplateCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class FinanceCategoryTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class FinanceCategoryTemplateOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    name: str
    sort_order: int
    credit_only: bool = False
    items: list[FinanceItemTemplateOut] = []


class FinanceTemplateOut(BaseModel):
    matter_sub_type_id: uuid.UUID
    categories: list[FinanceCategoryTemplateOut]


# ---------------------------------------------------------------------------
# Finance case data (per-case)
# ---------------------------------------------------------------------------

class FinanceItemCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    direction: Literal["debit", "credit"]
    sort_order: int = Field(default=0, ge=0)
    vat_treatment: Literal["included", "plus_vat"] | None = None

    model_config = {"extra": "forbid"}


class FinanceItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    direction: Literal["debit", "credit"] | None = None
    amount_pence: int | None = Field(default=None, ge=0)
    vat_pence: int | None = Field(default=None, ge=0)
    vat_treatment: Literal["included", "plus_vat"] | None = None
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class FinanceItemOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    template_item_id: uuid.UUID | None
    name: str
    direction: Literal["debit", "credit"]
    amount_pence: int | None
    vat_pence: int | None = None
    vat_treatment: Literal["included", "plus_vat"] | None = None
    sort_order: int


class FinanceCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}


class FinanceCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class FinanceCategoryOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    template_category_id: uuid.UUID | None
    name: str
    sort_order: int
    credit_only: bool = False
    items: list[FinanceItemOut] = []


class FinanceOut(BaseModel):
    case_id: uuid.UUID
    categories: list[FinanceCategoryOut]
    has_finance_preset: bool = False
    has_quote_snapshot: bool = False
    vat_rate_bps: int = 2000


# Sub-menu Events (admin templates + case rows)
class MatterSubTypeEventTemplateOut(BaseModel):
    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    name: str
    sort_order: int
    notify_on_day: bool = True
    notify_every_n: int | None = None
    notify_every_unit: Literal["days", "weeks", "months"] | None = None
    created_at: datetime
    updated_at: datetime


class CalendarEventTemplatePickOut(BaseModel):
    """Matter sub-type calendar line template for quick-fill on the main (CalDAV) calendar."""

    id: uuid.UUID
    matter_sub_type_id: uuid.UUID
    matter_sub_type_name: str
    name: str
    sort_order: int
    notify_on_day: bool = True
    notify_every_n: int | None = None
    notify_every_unit: Literal["days", "weeks", "months"] | None = None


class MatterSubTypeEventTemplateCreate(BaseModel):
    matter_sub_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0
    notify_on_day: bool = True
    notify_every_n: int | None = Field(default=None, ge=1, le=365)
    notify_every_unit: Literal["days", "weeks", "months"] | None = None


class MatterSubTypeEventTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None
    notify_on_day: bool | None = None
    notify_every_n: int | None = Field(default=None, ge=1, le=365)
    notify_every_unit: Literal["days", "weeks", "months"] | None = None


class CaseEventOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    template_id: uuid.UUID | None
    name: str
    sort_order: int
    event_date: date | None
    event_all_day: bool = True
    event_start_time: time | None = None
    """ISO start/end for CalDAV sync (UTC Z); only set when ``event_date`` is set."""
    calendar_block_start: str | None = None
    calendar_block_end: str | None = None
    calendar_block_all_day: bool | None = None
    track_in_calendar: bool = False
    calendar_event_uid: str | None = None
    email_alert_enabled: bool = False
    created_at: datetime
    updated_at: datetime


class CaseEventsOut(BaseModel):
    case_id: uuid.UUID
    events: list[CaseEventOut]


class CaseEventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    event_date: date | None = None
    event_all_day: bool = True
    event_start_time: time | None = None
    track_in_calendar: bool = False
    email_alert: bool = False

    @field_validator("event_date", mode="before")
    @classmethod
    def _empty_event_date_create(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v


class CaseEventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    event_date: date | None = None
    event_all_day: bool | None = None
    event_start_time: time | None = None
    track_in_calendar: bool | None = None
    calendar_event_uid: str | None = Field(default=None, max_length=512)
    email_alert: bool | None = None

    @field_validator("event_date", mode="before")
    @classmethod
    def _empty_event_date_to_none(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v


# ---------------------------------------------------------------------------
# Reports (ribbon)
# ---------------------------------------------------------------------------


class ReportFeeEarnerIdsIn(BaseModel):
    fee_earner_user_ids: list[uuid.UUID] = Field(min_length=1)

    model_config = {"extra": "forbid"}


class BillingReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> BillingReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class WipReportIn(ReportFeeEarnerIdsIn):
    as_of: date | None = None


class TimeRecordedReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> TimeRecordedReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class CasesReportIn(ReportFeeEarnerIdsIn):
    """Optional workflow status filter; omit or empty for all statuses."""

    statuses: list[str] | None = None


class CasesOpenedReportIn(ReportFeeEarnerIdsIn):
    date_from: date
    date_to: date
    include_quote: bool = True
    include_active: bool = True

    @model_validator(mode="after")
    def _dates(self) -> CasesOpenedReportIn:
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class EventsReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None
    template_ids: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def _dates(self) -> EventsReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class LedgerActivityReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None
    approved_only: bool = False

    @model_validator(mode="after")
    def _dates(self) -> LedgerActivityReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class AgedDebtReportIn(ReportFeeEarnerIdsIn):
    as_of: date | None = None


class ExceptionsReportIn(ReportFeeEarnerIdsIn):
    date_from: date | None = None
    date_to: date | None = None
    large_posting_min_pence: int = Field(default=500_000, ge=1)

    @model_validator(mode="after")
    def _dates(self) -> ExceptionsReportIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class ReconciliationPreviewOut(BaseModel):
    ledger_client_total_pence: int
    ledger_office_total_pence: int


class ClientAccountReconciliationOut(BaseModel):
    id: uuid.UUID
    period_end_date: date
    ledger_client_total_pence: int
    ledger_office_total_pence: int
    bank_statement_balance_pence: int
    difference_pence: int
    prepared_by_user_id: uuid.UUID
    prepared_by_name: str | None = None
    prepared_at: datetime
    approved_by_user_id: uuid.UUID | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    notes: str | None = None
    status: str


class ClientAccountReconciliationCreateIn(BaseModel):
    period_end_date: date
    bank_statement_balance_pence: int
    notes: str | None = Field(default=None, max_length=8000)


class ClientAccountReconciliationUpdateIn(BaseModel):
    bank_statement_balance_pence: int | None = None
    notes: str | None = Field(default=None, max_length=8000)
    refresh_ledger_totals: bool = True


class AccountantPackIn(ReportFeeEarnerIdsIn):
    period_end_date: date
    date_from: date | None = None
    date_to: date | None = None
    include_balances: bool = True
    include_billing: bool = True
    include_ledger_activity: bool = True
    include_aged_debt: bool = True
    include_exceptions: bool = False
    include_reconcile_doc: bool = True
    large_posting_min_pence: int = Field(default=500_000, ge=1)

    @model_validator(mode="after")
    def _dates(self) -> AccountantPackIn:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("Provide both activity date_from and date_to, or leave both empty.")
        return self


class AccountantPackSectionOut(BaseModel):
    key: str
    label: str
    included: bool
    row_count: int | None = None
    note: str | None = None


class AccountantPackPreviewOut(BaseModel):
    period_end_date: date
    activity_date_from: date
    activity_date_to: date
    fee_earner_count: int
    reconcile_doc_available: bool
    sections: list[AccountantPackSectionOut]


class FeeEarnerPickOut(BaseModel):
    id: uuid.UUID
    display_name: str
    email: EmailStr

    model_config = {"from_attributes": True}


class PortalConfigOut(BaseModel):
    firm_name: str
    portal_title: str
    portal_logo_url: str | None = None
    powered_by_label: str = "Powered by Canary Legal Software"
    powered_by_url: str = "https://canarylegalsoftware.co.uk"


class PortalAuthIn(BaseModel):
    access_code: str = Field(min_length=8, max_length=64)


class PortalGrantSummaryOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    case_title: str
    folder_path: str
    folder_label: str
    label: str
    can_download: bool
    can_upload: bool


class PortalAuthOut(BaseModel):
    session_token: str
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    focus_case_id: uuid.UUID | None = None
    staff_preview: bool = False


class PortalSessionOut(BaseModel):
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    staff_preview: bool = False


class PortalFileOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    folder_path: str
    folder_display: str = ""
    created_at: datetime
    updated_at: datetime


class PortalBrowseOut(BaseModel):
    subfolder: str
    breadcrumb: list[str]
    subfolders: list[str]
    files: list[PortalFileOut]
    pending_approvals: list[PortalQuoteDeliveryViewOut] = []
    pending_docusign_signings: list[PortalDocusignSigningOut] = []
    pending_portal_forms: list["PortalFormPendingOut"] = []


class PortalFormTemplateFieldIn(BaseModel):
    field_key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=500)
    field_type: Literal["section", "text", "textarea", "date", "select", "file"]
    help_text: str | None = Field(default=None, max_length=2000)
    required: bool = False
    sort_order: int = 0
    select_options: list[str] = Field(default_factory=list)


class PortalFormTemplateFieldOut(PortalFormTemplateFieldIn):
    id: uuid.UUID


class PortalFormTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    reference: str
    description: str | None = None
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    scope_summary: str = ""
    field_count: int = 0
    created_at: datetime
    updated_at: datetime


class PortalFormTemplateDetailOut(PortalFormTemplateOut):
    fields: list[PortalFormTemplateFieldOut] = []


class PortalFormTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    reference: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    fields: list[PortalFormTemplateFieldIn] = Field(default_factory=list)


class PortalFormTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    matter_head_type_id: uuid.UUID | None = None
    matter_sub_type_id: uuid.UUID | None = None
    fields: list[PortalFormTemplateFieldIn] | None = None


class PortalFormSendIn(BaseModel):
    template_id: uuid.UUID
    contact_id: uuid.UUID


class PortalFormSubmissionOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    template_id: uuid.UUID
    template_name: str
    template_reference: str
    contact_id: uuid.UUID
    contact_name: str
    status: str
    responses: dict = {}
    snapshot_file_id: uuid.UUID | None = None
    snapshot_filename: str = ""
    sent_at: datetime
    completed_at: datetime | None = None
    voided_at: datetime | None = None
    email_sent: bool = False
    email_skip_reason: str | None = None


class PortalFormFieldOut(BaseModel):
    field_key: str
    label: str
    field_type: str
    help_text: str | None = None
    required: bool
    sort_order: int
    select_options: list[str] = []


class PortalFormPendingOut(BaseModel):
    id: uuid.UUID
    template_name: str
    template_reference: str
    status: str
    sent_at: datetime
    case_id: uuid.UUID | None = None
    matter_label: str = ""


class PortalFormDetailOut(PortalFormSubmissionOut):
    description: str | None = None
    fields: list[PortalFormFieldOut] = []


class PortalFormSubmitIn(BaseModel):
    responses: dict = Field(default_factory=dict)


class PortalOtpRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PortalOtpVerifyIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=4, max_length=12)


class CasePortalNotifyFilesIn(BaseModel):
    folder_path: str = ""
    filenames: list[str] = Field(min_length=1)


class CasePortalNotifyFilesOut(BaseModel):
    contacts_notified: int
    alerts_skipped_reason: str | None = None


class CasePortalActivityOut(BaseModel):
    id: uuid.UUID
    action: str
    summary: str
    contact_name: str | None
    created_at: datetime


class CasePortalShareStatusOut(BaseModel):
    portal_enabled: bool
    active_grant_count: int
    contact_count: int


class CasePortalStaffUserOut(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str


class CasePortalNotificationSettingsOut(BaseModel):
    staff_user_ids: list[uuid.UUID]
    staff_users: list[CasePortalStaffUserOut] = Field(default_factory=list)


class CasePortalNotificationSettingsIn(BaseModel):
    staff_user_ids: list[uuid.UUID] = Field(default_factory=list)


class CasePortalPreviewContactOut(BaseModel):
    contact_id: uuid.UUID
    contact_name: str
    shared_folder_count: int
    pending_quote_count: int = 0
    pending_form_count: int = 0


class CasePortalPreviewIn(BaseModel):
    contact_id: uuid.UUID


class CasePortalPreviewOut(BaseModel):
    exchange_token: str
    contact_name: str
    preview_url: str


class PortalPreviewExchangeIn(BaseModel):
    exchange_token: str = Field(min_length=10, max_length=4096)


class PortalQuoteExchangeIn(BaseModel):
    exchange_token: str = Field(min_length=10, max_length=4096)


class PortalQuoteDeliveryViewOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    grant_id: uuid.UUID | None
    case_id: uuid.UUID | None = None
    case_title: str = ""
    original_filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    folder_display: str = ""
    status: str
    can_respond: bool
    decline_reason: str | None = None
    responded_at: datetime | None = None
    portal_pdf_available: bool = False


class PortalQuoteRespondIn(BaseModel):
    accepted: bool
    decline_reason: str | None = Field(default=None, max_length=2000)


class PortalQuoteExchangeOut(BaseModel):
    session_token: str
    contact_name: str
    grants: list[PortalGrantSummaryOut]
    quote: PortalQuoteDeliveryViewOut


class QuotePortalSendPreflightOut(BaseModel):
    alerts_configured: bool


class SendQuoteViaPortalIn(BaseModel):
    contact_id: uuid.UUID


class PortalQuoteTagUpdate(BaseModel):
    is_portal_quote: bool


class QuotePortalDeliveryOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    status: str
    sent_at: datetime
    responded_at: datetime | None = None
    decline_reason: str | None = None
    file_version_at_send: int
    email_sent: bool = False
    email_skip_reason: str | None = None
    portal_pdf_generated: bool = False


class PublishComposeIn(BaseModel):
    notify_portal_contacts: bool = False


class ContactPortalNotificationPrefsOut(BaseModel):
    notify_files_added: bool
    notify_folder_shared: bool


class ContactPortalNotificationPrefsIn(BaseModel):
    notify_files_added: bool | None = None
    notify_folder_shared: bool | None = None


class ContactPortalAccessOut(BaseModel):
    enabled: bool
    expires_at: datetime | None
    last_login_at: datetime | None
    locked_until: datetime | None
    has_access: bool
    access_code: str | None = None
    access_record_exists: bool = False
    notify_files_added: bool = True
    notify_folder_shared: bool = True


class ContactPortalAccessCreateOut(BaseModel):
    access_code: str
    enabled: bool
    expires_at: datetime | None
    email_sent: bool = False
    email_skip_reason: str | None = None


class ContactPortalAccessActionIn(BaseModel):
    send_email: bool = False


class ContactPortalAccessEmailIn(BaseModel):
    access_code: str = Field(min_length=4, max_length=64)


class ContactPortalAccessUpdateIn(BaseModel):
    enabled: bool | None = None
    expires_at: datetime | None = None


class ContactPortalGrantOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    case_id: uuid.UUID
    case_title: str
    folder_path: str
    label: str | None
    can_download: bool
    can_upload: bool
    expires_at: datetime | None
    created_at: datetime
    email_sent: bool = False
    email_skip_reason: str | None = None


class ContactPortalGrantCreateIn(BaseModel):
    case_id: uuid.UUID
    folder_path: str = ""
    label: str | None = Field(default=None, max_length=300)
    can_download: bool = True
    can_upload: bool = True
    expires_at: datetime | None = None
    send_email: bool = False


class ContactPortalGrantUpdateIn(BaseModel):
    folder_path: str | None = None
    label: str | None = Field(default=None, max_length=300)
    can_download: bool | None = None
    can_upload: bool | None = None
    expires_at: datetime | None = None


class DocusignIntegrationSettingsOut(BaseModel):
    enabled: bool
    use_demo: bool
    allow_tier_a: bool
    allow_tier_b: bool
    allow_tier_c: bool
    allow_wes: bool
    allow_qes: bool
    account_id: str | None = None
    integration_key: str | None = None
    user_id: str | None = None
    rsa_private_key_configured: bool = False
    connect_hmac_secret_configured: bool = False
    api_base_uri: str | None = None
    configured: bool = False
    cost_standard_pence: int | None = None
    cost_wes_pence: int | None = None
    cost_qes_pence: int | None = None


class DocusignIntegrationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    use_demo: bool | None = None
    allow_tier_a: bool | None = None
    allow_tier_b: bool | None = None
    allow_tier_c: bool | None = None
    allow_wes: bool | None = None
    allow_qes: bool | None = None
    account_id: str | None = Field(default=None, max_length=2000)
    integration_key: str | None = Field(default=None, max_length=2000)
    user_id: str | None = Field(default=None, max_length=2000)
    rsa_private_key: str | None = Field(default=None, max_length=20000)
    connect_hmac_secret: str | None = Field(default=None, max_length=2000)
    api_base_uri: str | None = Field(default=None, max_length=2000)
    cost_standard_pence: int | None = Field(default=None, ge=0)
    cost_wes_pence: int | None = Field(default=None, ge=0)
    cost_qes_pence: int | None = Field(default=None, ge=0)


class DocusignTemplateOut(BaseModel):
    template_id: str
    name: str
    description: str | None = None
    roles: list[str] = []


class DocusignSendRecipientIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    email: EmailStr
    routing_order: int = Field(default=1, ge=1, le=99)
    role_name: str | None = Field(default=None, max_length=100)
    case_contact_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


class DocusignSendIn(BaseModel):
    source_file_id: uuid.UUID | None = None
    template_id: str | None = Field(default=None, max_length=64)
    envelope_subject: str | None = Field(default=None, max_length=500)
    document_tier: Literal["a", "b", "c"] = "a"
    signature_level: Literal["standard", "wes", "qes"] = "standard"
    recipients: list[DocusignSendRecipientIn] = Field(min_length=1, max_length=20)


class DocusignVoidIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class DocusignSigningRecipientOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    routing_order: int
    role_name: str | None = None
    status: str
    completed_at: datetime | None = None


class DocusignSigningRequestOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    source_file_id: uuid.UUID | None = None
    source_filename: str = ""
    docusign_envelope_id: str | None = None
    docusign_template_id: str | None = None
    envelope_subject: str
    document_tier: str
    signature_level: str
    status: str
    status_detail: str | None = None
    signed_file_id: uuid.UUID | None = None
    certificate_file_id: uuid.UUID | None = None
    completed_at: datetime | None = None
    voided_at: datetime | None = None
    created_at: datetime | None = None
    recipients: list[DocusignSigningRecipientOut] = []


class DocusignStaffOptionsOut(BaseModel):
    enabled: bool
    allow_tier_a: bool
    allow_tier_b: bool
    allow_tier_c: bool
    allow_wes: bool
    allow_qes: bool


class DocusignMenuRowOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    case_number: str
    client_name: str | None = None
    matter_description: str = ""
    envelope_subject: str
    source_filename: str = ""
    status: str
    status_detail: str | None = None
    sent_by_display_name: str | None = None
    recipients_summary: str = ""
    created_at: datetime
    completed_at: datetime | None = None
    voided_at: datetime | None = None


class PortalDocusignSigningOut(BaseModel):
    id: uuid.UUID
    envelope_subject: str
    status: str
    can_sign: bool
    recipient_id: uuid.UUID
    sign_token: str


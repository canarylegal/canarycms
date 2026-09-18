from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
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
    accent: str = "#f0d010"
    mode: Literal["light", "dark"] = "light"
    page_bg: str = ""

class UserAppearanceUpdate(BaseModel):
    font: str = Field(default="", max_length=500)
    accent: str = Field(default="#f0d010", max_length=7)
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

class UserCalDAVStatusOut(BaseModel):
    enabled: bool
    caldav_url: str
    caldav_username: str

class UserCalDAVRevealIn(BaseModel):
    """Confirm Canary login password before revealing the stored CalDAV app password."""

    current_password: str = Field(min_length=1)

class UserCalDAVProvisionOut(BaseModel):
    caldav_url: str
    caldav_username: str
    caldav_password: str
    note: str = (
        "Save this password for your calendar app (not your Canary login). "
        "You can show it again later from User settings by confirming your Canary password."
    )

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

"""Org-wide e-mail integration: mailto vs Microsoft Graph, with optional DB-stored Entra credentials."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.permission_checks import user_may_access_accounts_workspace
from app.email_crypt import decrypt_password
from app.master_admin import load_master_admin_config, master_recovery_public_email
from app.models import EmailIntegrationSettings, File as DbFile, User, UserRole
from app.org_security import firm_mandates_second_factor, firm_password_rotation_policy, user_has_any_passkey
from app.schemas import UserPublic
from app.user_appearance import user_appearance_out
from app.user_ui_preferences import user_ui_preferences_out

log = logging.getLogger(__name__)

EmailIntegrationMode = Literal["mailto", "microsoft_graph"]

INTEGRATION_MAILTO = "mailto"
INTEGRATION_MICROSOFT_GRAPH = "microsoft_graph"


def get_email_integration_settings(db: Session) -> EmailIntegrationSettings:
    row = db.get(EmailIntegrationSettings, 1)
    if row is None:
        raise RuntimeError(
            "email_integration_settings row missing — run database migrations (alembic upgrade head).",
        )
    return row


def effective_graph_credentials(db: Session) -> tuple[str, str, str] | None:
    """Return (tenant_id, client_id, client_secret) when Graph mode and credentials resolve, else None."""
    row = get_email_integration_settings(db)
    if row.integration_mode != INTEGRATION_MICROSOFT_GRAPH:
        return None
    t_db = (row.graph_tenant_id or "").strip()
    c_db = (row.graph_client_id or "").strip()
    s_db = ""
    if row.graph_client_secret_enc:
        try:
            s_db = decrypt_password(row.graph_client_secret_enc).strip()
        except Exception:
            log.warning("Could not decrypt stored Graph client secret; falling back to env if present.")
            s_db = ""
    t = t_db or (os.getenv("CANARY_MS_GRAPH_TENANT_ID") or "").strip()
    c = c_db or (os.getenv("CANARY_MS_GRAPH_CLIENT_ID") or "").strip()
    s = s_db or (os.getenv("CANARY_MS_GRAPH_CLIENT_SECRET") or "").strip()
    if t and c and s:
        return (t, c, s)
    return None


def effective_outlook_web_mail_base(db: Session) -> str:
    row = get_email_integration_settings(db)
    b = (row.outlook_web_mail_base or "").strip()
    if b:
        return b.rstrip("/")
    return (os.getenv("CANARY_OUTLOOK_WEB_MAIL_BASE") or "https://outlook.office.com/mail").strip().rstrip("/")


def effective_outlook_web_mail_base_for_user(db: Session, user: User) -> str:
    """Org default, overridden by the user's Outlook web URL when they launch mail in the browser."""
    if (user.email_launch_preference or "").strip() == "outlook_web":
        personal = (user.email_outlook_web_url or "").strip()
        if personal:
            return personal.rstrip("/")
    return effective_outlook_web_mail_base(db)


def graph_mail_effective_configured(db: Session) -> bool:
    if get_email_integration_settings(db).integration_mode != INTEGRATION_MICROSOFT_GRAPH:
        return False
    return effective_graph_credentials(db) is not None


def user_public_email_fields(db: Session) -> dict[str, Any]:
    row = get_email_integration_settings(db)
    mode: EmailIntegrationMode = row.integration_mode  # type: ignore[assignment]
    return {
        "email_integration_mode": mode,
        "m365_graph_drafts_configured": graph_mail_effective_configured(db),
    }


def build_user_public(user: User, db: Session) -> UserPublic:
    prefs = user_ui_preferences_out(user.ui_preferences)
    saved_prefs = user.ui_preferences
    user.ui_preferences = prefs.model_dump()
    try:
        base = UserPublic.model_validate(user, from_attributes=True).model_dump()
    finally:
        user.ui_preferences = saved_prefs
    base["admin_console_access"] = user_effective_admin(user, db)
    base["accounts_workspace_access"] = user_may_access_accounts_workspace(user, db)
    base["organization_requires_second_factor"] = firm_mandates_second_factor(db)
    rotation_enabled, rotation_days = firm_password_rotation_policy(db)
    base["organization_requires_password_rotation"] = rotation_enabled
    base["password_rotation_days"] = rotation_days
    base["has_passkeys"] = user_has_any_passkey(db, user.id)
    base["pending_authenticator_setup"] = bool(user.totp_secret and not user.is_2fa_enabled)
    base["is_master_recovery"] = False
    base["appearance"] = user_appearance_out(user)
    base["ui_preferences"] = user_ui_preferences_out(user.ui_preferences)
    base.update(user_public_email_fields(db))
    if user.signature_file_id:
        sig = db.get(DbFile, user.signature_file_id)
        base["has_signature"] = bool(sig)
        base["signature_original_filename"] = sig.original_filename if sig else None
    else:
        base["has_signature"] = False
        base["signature_original_filename"] = None
    return UserPublic(**base)


def build_master_recovery_public(db: Session) -> UserPublic:
    cfg = load_master_admin_config()

    return UserPublic(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email=master_recovery_public_email(cfg.login),
        display_name="Master recovery",
        initials="MR",
        role=UserRole.admin,
        is_active=True,
        is_2fa_enabled=False,
        is_master_recovery=True,
        admin_console_access=False,
        organization_requires_second_factor=firm_mandates_second_factor(db),
        organization_requires_password_rotation=False,
        password_rotation_days=None,
        has_passkeys=False,
        pending_authenticator_setup=False,
        session_second_factor_verified=True,
        session_password_change_required=False,
        **user_public_email_fields(db),
    )

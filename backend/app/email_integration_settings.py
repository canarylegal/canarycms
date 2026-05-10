"""Org-wide e-mail integration: mailto vs Microsoft Graph, with optional DB-stored Entra credentials."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.email_crypt import decrypt_password
from app.models import EmailIntegrationSettings, User
from app.org_security import firm_mandates_second_factor, user_has_any_passkey
from app.schemas import UserPublic

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
    base = UserPublic.model_validate(user, from_attributes=True).model_dump()
    base["admin_console_access"] = user_effective_admin(user, db)
    base["organization_requires_second_factor"] = firm_mandates_second_factor(db)
    base["has_passkeys"] = user_has_any_passkey(db, user.id)
    base.update(user_public_email_fields(db))
    return UserPublic(**base)

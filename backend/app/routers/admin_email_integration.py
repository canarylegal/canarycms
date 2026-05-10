"""Admin: org-wide e-mail integration (mailto vs Microsoft Graph) and Entra app credentials."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.email_crypt import encrypt_password
from app.email_integration_settings import get_email_integration_settings
from app.models import User
from app.schemas import EmailIntegrationSettingsOut, EmailIntegrationSettingsUpdate

router = APIRouter(prefix="/admin/email", tags=["admin-email"])


def _row_to_out(row) -> EmailIntegrationSettingsOut:
    return EmailIntegrationSettingsOut(
        integration_mode=row.integration_mode,  # type: ignore[arg-type]
        graph_tenant_id=(row.graph_tenant_id or "").strip() or None,
        graph_client_id=(row.graph_client_id or "").strip() or None,
        graph_client_secret_configured=bool((row.graph_client_secret_enc or "").strip()),
        outlook_web_mail_base=(row.outlook_web_mail_base or "").strip() or None,
    )


@router.get("/settings", response_model=EmailIntegrationSettingsOut)
def get_email_settings(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> EmailIntegrationSettingsOut:
    row = get_email_integration_settings(db)
    return _row_to_out(row)


@router.put("/settings", response_model=EmailIntegrationSettingsOut)
def put_email_settings(
    payload: EmailIntegrationSettingsUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmailIntegrationSettingsOut:
    row = get_email_integration_settings(db)
    if payload.integration_mode is not None:
        row.integration_mode = payload.integration_mode
    if payload.graph_tenant_id is not None:
        t = payload.graph_tenant_id.strip()
        row.graph_tenant_id = t if t else None
    if payload.graph_client_id is not None:
        c = payload.graph_client_id.strip()
        row.graph_client_id = c if c else None
    if payload.graph_client_secret is not None:
        s = payload.graph_client_secret.strip()
        if s:
            row.graph_client_secret_enc = encrypt_password(s)
        else:
            row.graph_client_secret_enc = None
    if payload.outlook_web_mail_base is not None:
        b = payload.outlook_web_mail_base.strip()
        row.outlook_web_mail_base = b if b else None
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_out(row)

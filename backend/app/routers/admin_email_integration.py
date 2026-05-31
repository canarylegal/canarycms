"""Admin: org-wide e-mail integration (mailto vs Microsoft Graph) and Entra app credentials."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.email_crypt import encrypt_password
from app.email_integration_settings import get_email_integration_settings
from app.firm_email_service import FirmEmailMessage, firm_email_status, send_firm_email
from app.models import SmtpNotificationSettings, User
from app.schemas import (
    EmailIntegrationSettingsOut,
    EmailIntegrationSettingsUpdate,
    FirmAlertTestIn,
    SmtpNotificationSettingsOut,
    SmtpNotificationSettingsUpdate,
    SmtpNotificationTestIn,
)
from app.smtp_notification_settings import get_smtp_notification_settings
from app.smtp_send import send_smtp_message

router = APIRouter(prefix="/admin/email", tags=["admin-email"])


def _row_to_out(row, db: Session) -> EmailIntegrationSettingsOut:
    status = firm_email_status(db)
    return EmailIntegrationSettingsOut(
        integration_mode=row.integration_mode,  # type: ignore[arg-type]
        graph_tenant_id=(row.graph_tenant_id or "").strip() or None,
        graph_client_id=(row.graph_client_id or "").strip() or None,
        graph_client_secret_configured=bool((row.graph_client_secret_enc or "").strip()),
        outlook_web_mail_base=(row.outlook_web_mail_base or "").strip() or None,
        alerts_enabled=bool(row.alerts_enabled),
        alert_transport=row.alert_transport or "auto",  # type: ignore[arg-type]
        graph_send_mailbox=(row.graph_send_mailbox or "").strip() or None,
        graph_send_from_name=(row.graph_send_from_name or "").strip() or None,
        graph_alert_ready=bool(status["graph_ready"]),
        smtp_alert_ready=bool(status["smtp_ready"]),
        effective_alert_transport=status["effective_transport"],  # type: ignore[arg-type]
    )


@router.get("/settings", response_model=EmailIntegrationSettingsOut)
def get_email_settings(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> EmailIntegrationSettingsOut:
    row = get_email_integration_settings(db)
    return _row_to_out(row, db)


@router.put("/settings", response_model=EmailIntegrationSettingsOut)
def put_email_settings(
    payload: EmailIntegrationSettingsUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EmailIntegrationSettingsOut:
    row = get_email_integration_settings(db)
    data = payload.model_dump(exclude_unset=True)
    if "integration_mode" in data and data["integration_mode"] is not None:
        row.integration_mode = data["integration_mode"]
    if "graph_tenant_id" in data:
        t = (data["graph_tenant_id"] or "").strip()
        row.graph_tenant_id = t if t else None
    if "graph_client_id" in data:
        c = (data["graph_client_id"] or "").strip()
        row.graph_client_id = c if c else None
    if "graph_client_secret" in data:
        s = (data["graph_client_secret"] or "").strip()
        if s:
            row.graph_client_secret_enc = encrypt_password(s)
        else:
            row.graph_client_secret_enc = None
        data.pop("graph_client_secret", None)
    if "outlook_web_mail_base" in data:
        b = (data["outlook_web_mail_base"] or "").strip()
        row.outlook_web_mail_base = b if b else None
    if "alerts_enabled" in data and data["alerts_enabled"] is not None:
        row.alerts_enabled = bool(data["alerts_enabled"])
    if "alert_transport" in data and data["alert_transport"] is not None:
        row.alert_transport = data["alert_transport"]
    if "graph_send_mailbox" in data:
        m = (data["graph_send_mailbox"] or "").strip()
        row.graph_send_mailbox = m if m else None
    if "graph_send_from_name" in data:
        n = (data["graph_send_from_name"] or "").strip()
        row.graph_send_from_name = n if n else None
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_out(row, db)


def _smtp_to_out(row: SmtpNotificationSettings) -> SmtpNotificationSettingsOut:
    return SmtpNotificationSettingsOut(
        enabled=bool(row.enabled),
        host=(row.host or "").strip() or None,
        port=int(row.port or 587),
        use_tls=bool(row.use_tls),
        username=(row.username or "").strip() or None,
        password_configured=bool((row.password_enc or "").strip()),
        from_email=(row.from_email or "").strip() or None,
        from_name=(row.from_name or "").strip() or None,
    )


@router.get("/smtp-settings", response_model=SmtpNotificationSettingsOut)
def get_smtp_settings(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> SmtpNotificationSettingsOut:
    row = get_smtp_notification_settings(db)
    db.commit()
    return _smtp_to_out(row)


@router.put("/smtp-settings", response_model=SmtpNotificationSettingsOut)
def put_smtp_settings(
    payload: SmtpNotificationSettingsUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SmtpNotificationSettingsOut:
    row = get_smtp_notification_settings(db)
    data = payload.model_dump(exclude_unset=True)
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])
    if "host" in data:
        h = (data["host"] or "").strip()
        row.host = h if h else None
    if "port" in data and data["port"] is not None:
        row.port = int(data["port"])
    if "use_tls" in data and data["use_tls"] is not None:
        row.use_tls = bool(data["use_tls"])
    if "username" in data:
        u = (data["username"] or "").strip()
        row.username = u if u else None
    if "password" in data:
        p = (data["password"] or "").strip()
        row.password_enc = encrypt_password(p) if p else None
    if "from_email" in data:
        fe = (data["from_email"] or "").strip()
        row.from_email = fe if fe else None
    if "from_name" in data:
        fn = (data["from_name"] or "").strip()
        row.from_name = fn if fn else None
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _smtp_to_out(row)


@router.post("/smtp-test", status_code=status.HTTP_204_NO_CONTENT)
def post_smtp_test(
    body: SmtpNotificationTestIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    try:
        send_smtp_message(
            db,
            to_email=str(body.to_email),
            subject="Canary SMTP test",
            body="This message confirms outbound SMTP from Canary is working.",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    db.commit()


@router.post("/alerts-test", status_code=status.HTTP_204_NO_CONTENT)
def post_alerts_test(
    body: FirmAlertTestIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """Send via the configured alert transport (Graph when auto-preferred, else SMTP)."""
    try:
        send_firm_email(
            db,
            FirmEmailMessage(
                to_email=str(body.to_email),
                subject="Canary alert e-mail test",
                body_text="This message confirms automated alert e-mail from Canary is working.",
            ),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    db.commit()

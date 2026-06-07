"""Send plain-text e-mail via configured SMTP (TLS/STARTTLS)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.email_crypt import decrypt_password
from app.smtp_notification_settings import get_smtp_notification_settings


def send_smtp_message(
    db: Session,
    *,
    to_email: str,
    subject: str,
    body: str,
    body_html: str | None = None,
) -> None:
    """Send a plain-text message using org SMTP settings."""
    row = get_smtp_notification_settings(db)
    if not row.enabled:
        raise RuntimeError("SMTP notifications are disabled (Admin → E-mail).")
    host = (row.host or "").strip()
    if not host:
        raise RuntimeError("SMTP host is not configured.")
    from_email = (row.from_email or "").strip()
    if not from_email:
        raise RuntimeError("SMTP from address is not configured.")

    port = int(row.port or 587)
    use_tls = bool(row.use_tls)
    user = (row.username or "").strip() or None
    password = decrypt_password(row.password_enc) if row.password_enc else None

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{row.from_name} <{from_email}>" if (row.from_name or "").strip() else from_email
    msg["To"] = to_email
    msg.set_content(body)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    if use_tls and port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as smtp:
            if user and password:
                smtp.login(user, password)
            elif password:
                smtp.login(from_email, password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port) as smtp:
        if use_tls:
            context = ssl.create_default_context()
            smtp.starttls(context=context)
        if user and password:
            smtp.login(user, password)
        elif password:
            smtp.login(from_email, password)
        smtp.send_message(msg)

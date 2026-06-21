"""One-time authorization codes for Thunderbird / Outlook mail add-ins."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.canary_public_url import canary_public_url
from app.models import MailPluginAuthCode, User
from app.password_reset_service import login_access_token

PLUGIN_AUTH_TTL = timedelta(seconds=60)
_THUNDERBIRD_REDIRECT_RE = re.compile(
    r"^moz-extension://[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/auth-callback\.html$",
    re.IGNORECASE,
)
_THUNDERBIRD_HTTPS_CALLBACK_RE = re.compile(
    r"^https?://[a-zA-Z0-9._-]+(?::\d+)?/connect/mail-plugin/callback$",
    re.IGNORECASE,
)
_ALLOWED_CLIENTS = frozenset({"thunderbird", "outlook"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_plugin_client(client: str) -> str:
    c = (client or "").strip().lower()
    if c not in _ALLOWED_CLIENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported mail client.")
    return c


def validate_plugin_state(state: str) -> str:
    s = (state or "").strip()
    if len(s) < 16 or len(s) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", s):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter.")
    return s


def validate_plugin_redirect_uri(client: str, redirect_uri: str) -> str:
    uri = (redirect_uri or "").strip()
    if not uri:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri is required.")
    if client == "thunderbird":
        if _THUNDERBIRD_REDIRECT_RE.fullmatch(uri) or _THUNDERBIRD_HTTPS_CALLBACK_RE.fullmatch(uri):
            return uri
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid redirect URI for Thunderbird.",
        )
    base = canary_public_url().rstrip("/")
    expected = f"{base}/outlook-addin/auth-callback.html"
    if uri != expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid redirect URI for Outlook.",
        )
    return uri


def _purge_expired_codes(db: Session) -> None:
    db.execute(delete(MailPluginAuthCode).where(MailPluginAuthCode.expires_at < utcnow()))


def create_plugin_auth_code(
    db: Session,
    *,
    user: User,
    client: str,
    state: str,
    redirect_uri: str,
) -> str:
    _purge_expired_codes(db)
    client_norm = validate_plugin_client(client)
    state_norm = validate_plugin_state(state)
    redirect_norm = validate_plugin_redirect_uri(client_norm, redirect_uri)
    raw = secrets.token_urlsafe(32)
    row = MailPluginAuthCode(
        id=uuid.uuid4(),
        code_sha256=_hash_code(raw),
        user_id=user.id,
        client=client_norm,
        state=state_norm,
        redirect_uri=redirect_norm,
        expires_at=utcnow() + PLUGIN_AUTH_TTL,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.plugin.authorize",
        entity_type="user",
        entity_id=str(user.id),
        meta={"client": client_norm},
    )
    return raw


def exchange_plugin_auth_code(
    db: Session,
    *,
    client: str,
    state: str,
    code: str | None = None,
) -> str:
    client_norm = validate_plugin_client(client)
    state_norm = validate_plugin_state(state)
    raw = (code or "").strip()
    now = utcnow()
    if raw:
        digest = _hash_code(raw)
        row = db.execute(
            select(MailPluginAuthCode).where(
                MailPluginAuthCode.code_sha256 == digest,
                MailPluginAuthCode.client == client_norm,
                MailPluginAuthCode.state == state_norm,
                MailPluginAuthCode.consumed_at.is_(None),
                MailPluginAuthCode.expires_at >= now,
            )
        ).scalar_one_or_none()
    else:
        row = db.execute(
            select(MailPluginAuthCode)
            .where(
                MailPluginAuthCode.client == client_norm,
                MailPluginAuthCode.state == state_norm,
                MailPluginAuthCode.consumed_at.is_(None),
                MailPluginAuthCode.expires_at >= now,
            )
            .order_by(MailPluginAuthCode.created_at.desc())
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authorization code.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authorization code.")
    row.consumed_at = now
    db.add(row)
    token = login_access_token(db, user, mfa_verified=True)
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.plugin.token",
        entity_type="user",
        entity_id=str(user.id),
        meta={"client": client_norm},
    )
    return token

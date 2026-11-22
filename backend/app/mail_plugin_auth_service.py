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

# Allow browser sign-in and MFA before the client redeems the returned code.
PLUGIN_AUTH_TTL = timedelta(minutes=5)
_THUNDERBIRD_REDIRECT_RE = re.compile(
    r"^moz-extension://[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/auth-callback\.html$",
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
        if (_THUNDERBIRD_REDIRECT_RE.fullmatch(uri)
                or uri == canary_public_url().rstrip("/") + "/connect/mail-plugin/callback"):
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


def _purge_expired_codes(db: Session, user_id: uuid.UUID) -> None:
    db.execute(delete(MailPluginAuthCode).where(
        MailPluginAuthCode.user_id == user_id, MailPluginAuthCode.expires_at < utcnow()))


def create_plugin_auth_code(
    db: Session,
    *,
    user: User,
    client: str,
    state: str,
    redirect_uri: str,
) -> str:
    _purge_expired_codes(db, user.id)
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
        auth_token_version=int(user.auth_token_version),
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
    if not raw:
        raise HTTPException(401, "An authorization code is required. Reconnect using an updated mail client.")
    digest = _hash_code(raw)
    identity = db.execute(select(MailPluginAuthCode.id, MailPluginAuthCode.user_id).where(
        MailPluginAuthCode.code_sha256 == digest, MailPluginAuthCode.client == client_norm,
        MailPluginAuthCode.state == state_norm,
    )).first()
    if identity is None:
        raise HTTPException(401, "Invalid or expired authorization code.")
    # Match enrollment/authorization lock order. Recheck receipt and expiry after
    # waiting: concurrent redemption must never mint a second staff session.
    user = db.execute(select(User).where(User.id == identity.user_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one_or_none()
    now = utcnow()
    row = db.execute(select(MailPluginAuthCode).where(
        MailPluginAuthCode.id == identity.id, MailPluginAuthCode.consumed_at.is_(None),
        MailPluginAuthCode.expires_at >= now,
    ).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if (row is None or user is None or not user.is_active
            or row.auth_token_version is None
            or row.auth_token_version != int(user.auth_token_version)):
        raise HTTPException(401, "Invalid or expired authorization code.")
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

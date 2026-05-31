import os
import time
from dataclasses import dataclass

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext


# Use PBKDF2 to avoid bcrypt backend quirks in containers and the 72-byte limit.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


JWT_SECRET = _require_env("JWT_SECRET")
JWT_ALG = "HS256"
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", "28800"))  # 8h


def create_access_token(*, user_id: str, role: str, mfa_verified: bool = True, password_ok: bool = True) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "role": role,
        # Under org mandate, API access requires mfa_verified=True (passkey sign-in or password+authenticator).
        "mfa": bool(mfa_verified),
        # When False, user must change password before using the rest of the app (rotation policy).
        "pwd": bool(password_ok),
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    role: str
    """Present on newer JWTs only; ``None`` means legacy token without an ``mfa`` claim."""
    mfa_verified: bool | None = None
    """Present on newer JWTs only; ``None`` means legacy token without a ``pwd`` claim."""
    password_ok: bool | None = None


EML_OPEN_TTL_SECONDS = int(os.getenv("EML_OPEN_TTL_SECONDS", "120"))


@dataclass(frozen=True)
class EmlOpenTokenPayload:
    user_id: str
    case_id: str
    file_id: str


def create_eml_open_token(*, user_id: str, case_id: str, file_id: str) -> str:
    """Short-lived JWT for GET without Authorization (opens mail client / download hand-off)."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "purpose": "eml_open",
        "case_id": case_id,
        "file_id": file_id,
        "iat": now,
        "exp": now + EML_OPEN_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


COMPOSE_HANDOFF_TTL_SECONDS = int(os.getenv("COMPOSE_HANDOFF_TTL_SECONDS", "900"))


@dataclass(frozen=True)
class ComposeHandoffTokenPayload:
    user_id: str
    case_id: str
    to: str
    subject: str
    body: str
    attachment_file_ids: tuple[str, ...]


def create_compose_handoff_token(
    *,
    user_id: str,
    case_id: str,
    to: str,
    subject: str,
    body: str,
    attachment_file_ids: list[str],
) -> str:
    """Short-lived JWT for Thunderbird (or other clients) to fetch a compose bundle."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "purpose": "compose_handoff",
        "case_id": case_id,
        "to": to,
        "subject": subject,
        "body": body,
        "attachment_file_ids": attachment_file_ids,
        "iat": now,
        "exp": now + COMPOSE_HANDOFF_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_compose_handoff_token(token: str) -> ComposeHandoffTokenPayload:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise ValueError("Invalid or expired token") from e
    if payload.get("purpose") != "compose_handoff":
        raise ValueError("Invalid token")
    sub = payload.get("sub")
    case_id = payload.get("case_id")
    if not isinstance(sub, str) or not isinstance(case_id, str):
        raise ValueError("Invalid token payload")
    to = payload.get("to")
    subject = payload.get("subject")
    body = payload.get("body")
    raw_ids = payload.get("attachment_file_ids")
    if not isinstance(to, str) or not isinstance(subject, str) or not isinstance(body, str):
        raise ValueError("Invalid token payload")
    ids: list[str] = []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            if isinstance(x, str) and x.strip():
                ids.append(x.strip())
    return ComposeHandoffTokenPayload(
        user_id=sub,
        case_id=case_id,
        to=to,
        subject=subject,
        body=body,
        attachment_file_ids=tuple(ids),
    )


def decode_eml_open_token(token: str) -> EmlOpenTokenPayload:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise ValueError("Invalid or expired token") from e
    if payload.get("purpose") != "eml_open":
        raise ValueError("Invalid token")
    case_id = payload.get("case_id")
    file_id = payload.get("file_id")
    sub = payload.get("sub")
    if not isinstance(case_id, str) or not isinstance(file_id, str) or not isinstance(sub, str):
        raise ValueError("Invalid token payload")
    return EmlOpenTokenPayload(user_id=sub, case_id=case_id, file_id=file_id)


PORTAL_SESSION_TTL_SECONDS = int(os.getenv("PORTAL_SESSION_TTL_SECONDS", "28800"))  # 8h


@dataclass(frozen=True)
class PortalSessionPayload:
    contact_id: str


def create_portal_session_token(*, contact_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": contact_id,
        "purpose": "portal",
        "iat": now,
        "exp": now + PORTAL_SESSION_TTL_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_portal_session_token(token: str) -> PortalSessionPayload:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise ValueError("Invalid or expired session") from e
    if payload.get("purpose") != "portal":
        raise ValueError("Invalid session")
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise ValueError("Invalid session")
    return PortalSessionPayload(contact_id=sub)


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise ValueError("Invalid token") from e

    sub = payload.get("sub")
    role = payload.get("role")
    if not isinstance(sub, str) or not isinstance(role, str):
        raise ValueError("Invalid token payload")
    mfa_raw = payload.get("mfa")
    mfa_verified: bool | None
    if mfa_raw is True:
        mfa_verified = True
    elif mfa_raw is False:
        mfa_verified = False
    else:
        mfa_verified = None
    pwd_raw = payload.get("pwd")
    password_ok: bool | None
    if pwd_raw is True:
        password_ok = True
    elif pwd_raw is False:
        password_ok = False
    else:
        password_ok = None
    return TokenPayload(user_id=sub, role=role, mfa_verified=mfa_verified, password_ok=password_ok)


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(*, secret: str, email: str, issuer: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(*, secret: str, code: str) -> bool:
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False

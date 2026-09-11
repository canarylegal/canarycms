"""HttpOnly session cookie for staff browser JWTs (XSS-resistant vs localStorage)."""

from __future__ import annotations

import os

from fastapi import Request, Response

from app.security import JWT_TTL_SECONDS

# Readable by JS must remain false — mail add-ins still use Authorization Bearer from their own storage.
SESSION_COOKIE_NAME = "canary_session"


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def session_cookies_enabled() -> bool:
    """Default on. Set CANARY_SESSION_COOKIE=0 to disable (Bearer-only, e.g. unusual reverse proxies)."""
    return _truthy(os.getenv("CANARY_SESSION_COOKIE", "1"))


def _cookie_secure(request: Request | None = None) -> bool:
    explicit = (os.getenv("CANARY_SESSION_COOKIE_SECURE") or "").strip().lower()
    if explicit in ("1", "true", "yes", "on"):
        return True
    if explicit in ("0", "false", "no", "off"):
        return False
    if request is not None:
        if request.url.scheme == "https":
            return True
        xf = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        if xf == "https":
            return True
    public = (os.getenv("CANARY_PUBLIC_URL") or "").strip().lower()
    return public.startswith("https://")


def attach_session_cookie(response: Response, token: str, *, request: Request | None = None) -> None:
    if not session_cookies_enabled():
        return
    raw = (token or "").strip()
    if not raw:
        return
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, *, request: Request | None = None) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )


def session_token_from_request(request: Request) -> str | None:
    if not session_cookies_enabled():
        return None
    raw = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    return raw or None

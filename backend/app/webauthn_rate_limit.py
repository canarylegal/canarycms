"""Atomic, account-independent request budgets for public passkey endpoints."""
import hashlib
import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth_rate_limit import _int_env
from app.models import AuthRateLimitEntry


def limit_passkey_request(db: Session, request: Request, email: str, phase: str) -> None:
    # Uvicorn resolves trusted proxies; never trust arbitrary forwarded headers here.
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    window = timedelta(seconds=_int_env("WEBAUTHN_RATE_WINDOW_SECONDS", 60))
    row = AuthRateLimitEntry
    db.execute(delete(row).where(row.scope.like("webauthn_%"), row.locked_until < now - timedelta(minutes=10)))
    for bucket, key, default in [("ip", ip, 60), ("account_ip", ip + "\0" + email, 10)]:
        limit = _int_env(f"WEBAUTHN_{phase.upper()}_{bucket.upper()}_MAX_ATTEMPTS", default)
        stmt = insert(row).values(id=uuid.uuid4(), scope=f"webauthn_{phase}_{bucket}",
            identifier=hashlib.sha256(key.encode()).hexdigest(), failed_attempts=1,
            locked_until=now + window, created_at=now, updated_at=now)
        stmt = stmt.on_conflict_do_update(index_elements=[row.scope, row.identifier], set_={
            "failed_attempts": case((row.locked_until <= now, 1), else_=row.failed_attempts + 1),
            "locked_until": case((row.locked_until <= now, now + window), else_=row.locked_until),
            "updated_at": now,
        }).returning(row.failed_attempts, row.locked_until)
        count, until = db.execute(stmt).one()
        db.commit()
        if count > limit:
            raise HTTPException(429, "Too many passkey sign-in attempts. Try again later.",
                headers={"Retry-After": str(max(1, math.ceil((until - now).total_seconds())))})

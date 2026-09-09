from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.timeutil import utcnow

_META_MAX_CHARS = 8000


def _safe_meta_json(meta: dict[str, Any]) -> str:
    """Serialize meta to JSON, truncating values so the result stays valid JSON."""
    raw = json.dumps(meta, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(raw) <= _META_MAX_CHARS:
        return raw

    trimmed: dict[str, Any] = {"_truncated": True}
    # Prefer keeping short scalar keys; drop oversized nested payloads.
    for key, value in meta.items():
        if key.startswith("_"):
            continue
        piece = json.dumps({key: value}, ensure_ascii=False, separators=(",", ":"), default=str)
        candidate = json.dumps({**trimmed, key: value}, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(candidate) > _META_MAX_CHARS:
            if isinstance(value, str):
                budget = max(32, _META_MAX_CHARS - len(json.dumps({**trimmed, key: ""}, ensure_ascii=False)) - 20)
                trimmed[key] = value[:budget] + "…"
                cont = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"), default=str)
                if len(cont) <= _META_MAX_CHARS:
                    continue
            trimmed[key] = "<omitted>"
            cont = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"), default=str)
            if len(cont) > _META_MAX_CHARS:
                trimmed.pop(key, None)
            continue
        trimmed[key] = value
        _ = piece  # silence unused in some linters
    out = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(out) > _META_MAX_CHARS:
        return json.dumps({"_truncated": True, "_note": "meta omitted"}, ensure_ascii=False, separators=(",", ":"))
    return out


def log_event(
    db: Session,
    *,
    actor_user_id,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Queue an audit row on the caller's session.

    Does not commit. Request handlers using ``get_db`` get an automatic commit on
    successful response. Prefer putting business mutations and ``log_event`` in the
    same transaction, then a single ``db.commit()``, for sensitive operations.
    """
    meta_json = None
    if meta is not None:
        # Never store secrets; keep it short and structured.
        meta_json = _safe_meta_json(meta)

    ev = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        user_agent=(user_agent[:300] if user_agent else None),
        meta_json=meta_json,
        created_at=utcnow(),
    )
    db.add(ev)
    db.flush()

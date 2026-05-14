"""Background Docker Compose updates for admin GUI (avoids long HTTP requests / proxy timeouts).

State is kept in-process. Use a **single** API worker process (default ``uvicorn`` without ``--workers``)
so job status and POST /trigger stay consistent. Multiple workers would each have separate job memory.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.audit import log_event
from app.db import SessionLocal
from app.local_compose_update import run_compose_update

_PHASE = Literal["idle", "running", "succeeded", "failed"]

_lock = threading.Lock()
_job_id: str | None = None
_phase: _PHASE = "idle"
_started_at: str | None = None
_finished_at: str | None = None
_message: str | None = None
_error_detail: str | None = None
_log_excerpt: str | None = None


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _excerpt_from_journal(journal: list[str], extra: str | None = None) -> str:
    parts: list[str] = []
    if journal:
        parts.append("\n".join(journal))
    if extra:
        parts.append(extra)
    raw = "\n\n".join(p for p in parts if p).strip()
    if len(raw) > 12_000:
        return raw[-12_000:]
    return raw


def get_compose_job_public() -> dict[str, Any]:
    """Safe fields for ``GET /admin/deploy/compose-job`` (no secrets)."""
    with _lock:
        return {
            "status": _phase,
            "job_id": _job_id,
            "started_at": _started_at,
            "finished_at": _finished_at,
            "message": _message,
            "error_detail": _error_detail,
            "log_excerpt": _log_excerpt,
        }


def try_start_compose_job(
    *,
    actor_user_id: int,
    ip: str | None,
    user_agent: str | None,
    profiles: tuple[str, ...],
) -> str | None:
    """Start a background compose update if idle. Returns ``job_id`` or ``None`` if busy."""
    global _job_id, _phase, _started_at, _finished_at, _message, _error_detail, _log_excerpt
    with _lock:
        if _phase == "running":
            return None
        jid = uuid.uuid4().hex[:12]
        _job_id = jid
        _phase = "running"
        _started_at = _utc_iso()
        _finished_at = None
        _message = None
        _error_detail = None
        _log_excerpt = None

    meta = {"profiles": list(profiles)}

    def _worker() -> None:
        global _phase, _finished_at, _message, _error_detail, _log_excerpt
        journal: list[str] = []
        try:
            run_compose_update(journal=journal)
        except BaseException as e:
            err_s = str(e).strip() or type(e).__name__
            excerpt = _excerpt_from_journal(journal, err_s)
            with _lock:
                _phase = "failed"
                _finished_at = _utc_iso()
                _message = None
                _error_detail = err_s[:4000]
                _log_excerpt = excerpt or None
            return

        excerpt = _excerpt_from_journal(journal, None)
        with _lock:
            _phase = "succeeded"
            _finished_at = _utc_iso()
            _message = (
                "Docker Compose finished (git pull if enabled, build --pull, up -d). "
                "Reload the app after containers restart."
            )
            _error_detail = None
            _log_excerpt = excerpt or None

        db = SessionLocal()
        try:
            log_event(
                db,
                actor_user_id=actor_user_id,
                action="admin_compose_update",
                entity_type="docker_compose",
                entity_id="compose_pull_build_up",
                ip=ip,
                user_agent=user_agent,
                meta={**meta, "job_id": jid, "async": True},
            )
        finally:
            db.close()

    t = threading.Thread(target=_worker, name="canary-compose-deploy", daemon=True)
    t.start()
    return jid


@dataclass
class ComposeJobStartResult:
    job_id: str


def start_or_busy(
    *,
    actor_user_id: int,
    ip: str | None,
    user_agent: str | None,
) -> ComposeJobStartResult | Literal["busy"]:
    prof_raw = (os.getenv("CANARY_COMPOSE_PROFILES") or "prod").strip()
    profiles = tuple(p.strip() for p in prof_raw.replace(",", " ").split() if p.strip()) or ("prod",)
    jid = try_start_compose_job(
        actor_user_id=actor_user_id,
        ip=ip,
        user_agent=user_agent,
        profiles=profiles,
    )
    if jid is None:
        return "busy"
    return ComposeJobStartResult(job_id=jid)

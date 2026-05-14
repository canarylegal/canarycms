"""Background Docker Compose updates for admin GUI (avoids long HTTP requests / proxy timeouts).

Job status is persisted to JSON so it survives **backend container recreation** during
``docker compose up -d``. We write to both the compose project mount (if configured) and
``FILES_ROOT`` (typically ``/data/files``, a Docker volume) so a bind-mount permission quirk
cannot silently drop updates.

Use a **single** API worker process (default ``uvicorn`` without ``--workers``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.audit import log_event
from app.db import SessionLocal
from app.local_compose_update import load_compose_update_config, run_compose_update

log = logging.getLogger(__name__)

_PHASE = Literal["idle", "running", "succeeded", "failed"]

_lock = threading.Lock()
_job_id: str | None = None
_phase: _PHASE = "idle"
_started_at: str | None = None
_finished_at: str | None = None
_message: str | None = None
_error_detail: str | None = None
_log_excerpt: str | None = None

_STATE_NAME = ".canary-compose-job-state.json"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host_boot_id() -> str:
    """Linux container boot id; changes when this container is recreated."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


def _state_paths() -> list[Path]:
    """All locations we mirror job state (first writable wins for reads by mtime)."""
    paths: list[Path] = []
    cfg = load_compose_update_config()
    if cfg is not None:
        paths.append(cfg.project_dir / _STATE_NAME)
    files_root = (os.getenv("FILES_ROOT") or "/data/files").strip()
    if files_root:
        p = Path(files_root) / _STATE_NAME
        if p not in paths:
            paths.append(p)
    return paths


def _read_one(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _read_disk_state() -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_mtime = -1.0
    for p in _state_paths():
        row = _read_one(p)
        if not row:
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            mt = 0.0
        if mt > best_mtime:
            best_mtime = mt
            best = row
    return best


def _write_disk_state(data: dict[str, Any]) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    for p in _state_paths():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(p)
        except OSError as e:
            log.warning("compose job state write failed (%s): %s", p, e)


def _memory_public() -> dict[str, Any]:
    return {
        "status": _phase,
        "job_id": _job_id,
        "started_at": _started_at,
        "finished_at": _finished_at,
        "message": _message,
        "error_detail": _error_detail,
        "log_excerpt": _log_excerpt,
    }


def get_compose_job_public() -> dict[str, Any]:
    """Safe fields for ``GET /admin/deploy/compose-job`` (no secrets)."""
    disk = _read_disk_state()
    current_boot = _host_boot_id()

    with _lock:
        mem = _memory_public()

    if disk:
        dst = str(disk.get("status") or "")
        disk_boot = str(disk.get("host_boot_id") or "")
        if dst == "running" and current_boot and disk_boot and disk_boot != current_boot:
            return {
                "status": "failed",
                "job_id": disk.get("job_id"),
                "started_at": disk.get("started_at"),
                "finished_at": _utc_iso(),
                "message": None,
                "error_detail": (
                    "This API container restarted during the update (expected when Docker recreates "
                    "the backend). Check ``docker compose ps`` on the host; reload the app if services are healthy."
                ),
                "log_excerpt": None,
            }
        if dst in ("succeeded", "failed"):
            return {
                "status": dst,
                "job_id": disk.get("job_id"),
                "started_at": disk.get("started_at"),
                "finished_at": disk.get("finished_at"),
                "message": disk.get("message"),
                "error_detail": disk.get("error_detail"),
                "log_excerpt": disk.get("log_excerpt"),
            }
        if dst == "running" and disk_boot == current_boot:
            return mem

    return mem


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


def _persist_from_globals() -> None:
    payload = {
        "status": _phase,
        "job_id": _job_id,
        "started_at": _started_at,
        "finished_at": _finished_at,
        "message": _message,
        "error_detail": _error_detail,
        "log_excerpt": _log_excerpt,
        "host_boot_id": _host_boot_id(),
    }
    _write_disk_state(payload)


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
        _persist_from_globals()

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
                _persist_from_globals()
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
            _persist_from_globals()

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

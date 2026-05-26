"""Background Docker Compose updates for admin GUI (avoids long HTTP requests / proxy timeouts).

Job status is persisted to JSON under ``<compose project>/.canary/runtime`` so it survives
**backend container recreation** during ``docker compose up -d`` (never under ``FILES_ROOT``).

Use a **single** API worker process (default ``uvicorn`` without ``--workers``).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.audit import log_event
from app.db import SessionLocal
from app.compose_runtime import (
    compose_job_state_path,
    legacy_compose_job_state_paths,
    resolve_compose_up_marker,
)
from app.local_compose_update import (
    compose_runner_container_name,
    docker_inspect_container_state,
    load_compose_update_config,
    run_compose_update,
)

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
_runner_expected: bool = False



def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _started_age_seconds(started_at: str | None) -> float | None:
    if not started_at:
        return None
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except ValueError:
        return None


def _running_payload_from_disk(disk: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "running",
        "job_id": disk.get("job_id"),
        "started_at": disk.get("started_at"),
        "finished_at": None,
        "message": None,
        "error_detail": None,
        "log_excerpt": None,
    }


def _api_restarted_since_job(disk: dict[str, Any]) -> bool:
    """True when this API process did not start the in-flight job (e.g. backend recreated during ``compose up``)."""
    disk_boot = str(disk.get("host_boot_id") or "").strip()
    current_boot = _host_boot_id()
    return bool(disk_boot and current_boot and disk_boot != current_boot)


def reconcile_compose_job_state() -> None:
    """Finalize a job from detached-runner marker files or stale ``running`` disk rows."""
    global _job_id, _phase, _started_at, _finished_at, _message, _error_detail, _log_excerpt, _runner_expected

    disk = _read_disk_state()
    if not disk or str(disk.get("status") or "") != "running":
        return
    jid = str(disk.get("job_id") or "").strip()
    if not jid:
        return

    api_restarted = _api_restarted_since_job(disk)

    with _lock:
        guard_worker = _phase == "running" and _job_id == jid
    if api_restarted:
        # Worker thread died with the previous container; only the detached runner / marker can finish this job.
        guard_worker = False

    name = compose_runner_container_name(jid)
    runner_on_disk = bool(disk.get("runner_expected"))
    marker = resolve_compose_up_marker(jid)

    def _persist_terminal(*, ok: bool, err: str | None, excerpt: str | None) -> None:
        global _job_id, _phase, _started_at, _finished_at, _message, _error_detail, _log_excerpt, _runner_expected
        with _lock:
            _job_id = jid
            _runner_expected = False
            _phase = "succeeded" if ok else "failed"
            _finished_at = _utc_iso()
            if _started_at is None:
                sa = disk.get("started_at")
                if sa:
                    _started_at = str(sa)
            if ok:
                _message = (
                    "Docker Compose finished (git pull if enabled, build --pull, up -d). "
                    "Reload the app after containers restart."
                )
                _error_detail = None
            else:
                _message = None
                _error_detail = (err or "Compose update failed")[:4000]
            _log_excerpt = excerpt
            _persist_from_globals()
            if ok:
                try:
                    from app.build_metadata import invalidate_live_compose_repo_head_cache

                    invalidate_live_compose_repo_head_cache()
                except Exception:
                    pass

    if marker is not None:
        try:
            row = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            row = {}
        # Do not let an in-process "running" job block consuming a **success** marker: the worker may be
        # sleeping in its poll loop, or another request may reconcile first. Failure markers are left to
        # the worker so it can attach logs / raise.
        if guard_worker and not bool(row.get("ok")):
            return
        try:
            marker.unlink()
        except OSError:
            pass
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True, text=True, timeout=30)
        ok = bool(row.get("ok"))
        err = None if ok else f"docker compose up -d failed (rc={row.get('rc')})"
        _persist_terminal(ok=ok, err=err, excerpt=None)
        return

    if guard_worker:
        return

    st = docker_inspect_container_state(name)
    if st is not None and st[0] in ("created", "running"):
        return

    if st is not None and st[0] == "exited":
        lg = subprocess.run(
            ["docker", "logs", "--tail", "200", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        tail = ((lg.stdout or "") + (lg.stderr or "")).strip()[-8000:]
        _persist_terminal(
            ok=False,
            err="Compose runner exited without writing a result marker.",
            excerpt=tail or None,
        )
        return

    age = _started_age_seconds(str(disk.get("started_at") or ""))
    if age is None:
        return
    if not runner_on_disk and age > 4000:
        _persist_terminal(
            ok=False,
            err="Compose update did not dispatch an isolated ``up`` runner (build may have stalled).",
            excerpt=None,
        )
        return
    stale_after = 15 if api_restarted else 180
    if runner_on_disk and age > stale_after and st is None:
        for _ in range(5):
            if resolve_compose_up_marker(jid) is not None:
                reconcile_compose_job_state()
                return
            time.sleep(1.0)
        if api_restarted:
            err = (
                "The API container restarted during the update (normal for Docker Compose). "
                "Refresh this page and check Admin → Deploy or ``docker compose ps``. "
                "If the site loads, the update may have finished; otherwise run Compose update again."
            )
        else:
            err = "Compose runner container disappeared before reporting completion. Check ``docker compose ps``."
        _persist_terminal(
            ok=False,
            err=err,
            excerpt=None,
        )


def _host_boot_id() -> str:
    """Linux container boot id; changes when this container is recreated."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


def _state_write_path() -> Path:
    """Where new job state is persisted (never ``FILES_ROOT``)."""
    return compose_job_state_path()


def _state_read_paths() -> list[Path]:
    """Primary path plus legacy locations (read-only reconciliation after upgrade)."""
    primary = _state_write_path()
    paths = [primary]
    for legacy in legacy_compose_job_state_paths():
        if legacy not in paths:
            paths.append(legacy)
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
    """Return the best job row from disk.

    The primary ``.canary/runtime/compose-job-state.json`` wins when present so stale legacy
    mirrors (project root or old ``FILES_ROOT`` copies) cannot mask an in-flight job.
    """
    primary_path = _state_write_path()
    primary = _read_one(primary_path)
    if primary is not None:
        return primary

    rows: list[tuple[float, dict[str, Any]]] = []
    for p in _state_read_paths():
        if p == primary_path:
            continue
        row = _read_one(p)
        if not row:
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            mt = 0.0
        rows.append((mt, row))
    if not rows:
        return None
    terminal = [(mt, r) for mt, r in rows if str(r.get("status") or "") in ("succeeded", "failed")]
    if terminal:
        return max(terminal, key=lambda x: x[0])[1]
    return max(rows, key=lambda x: x[0])[1]


def compose_job_disk_says_running() -> bool:
    d = _read_disk_state()
    return bool(d and str(d.get("status") or "") == "running")


def _write_disk_state(data: dict[str, Any]) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    p = _state_write_path()
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
    reconcile_compose_job_state()
    disk = _read_disk_state()
    # Marker can land just after a reconcile pass (slow volume / runner tail). Peek once more.
    if disk and str(disk.get("status") or "") == "running":
        jid = str(disk.get("job_id") or "").strip()
        if jid:
            mp = resolve_compose_up_marker(jid)
            if mp is not None:
                try:
                    if bool(json.loads(mp.read_text(encoding="utf-8")).get("ok")):
                        time.sleep(0.2)
                        reconcile_compose_job_state()
                        disk = _read_disk_state()
                except (OSError, json.JSONDecodeError):
                    pass

    with _lock:
        mem = _memory_public()

    if not disk:
        return mem

    dst = str(disk.get("status") or "")
    # Prefer in-process terminal state if disk mirrors are stale (e.g. one path write failed).
    if (
        mem.get("job_id")
        and str(mem.get("job_id")) == str(disk.get("job_id") or "")
        and str(mem.get("status") or "") in ("succeeded", "failed")
        and dst == "running"
    ):
        ms = str(mem.get("status") or "")
        return {
            "status": ms,
            "job_id": mem.get("job_id"),
            "started_at": mem.get("started_at") or disk.get("started_at"),
            "finished_at": mem.get("finished_at"),
            "message": mem.get("message"),
            "error_detail": mem.get("error_detail"),
            "log_excerpt": mem.get("log_excerpt"),
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
    if dst == "running":
        if str(mem.get("status") or "") == "running":
            return mem
        return _running_payload_from_disk(disk)
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
        "runner_expected": _runner_expected,
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
    global _job_id, _phase, _started_at, _finished_at, _message, _error_detail, _log_excerpt, _runner_expected

    reconcile_compose_job_state()

    with _lock:
        if _phase == "running":
            return None
        d = _read_disk_state()
        if d and str(d.get("status") or "") == "running":
            other = str(d.get("job_id") or "").strip()
            if other:
                st = docker_inspect_container_state(compose_runner_container_name(other))
                if st is not None and st[0] in ("created", "running"):
                    return None

        jid = uuid.uuid4().hex[:12]
        _job_id = jid
        _phase = "running"
        _started_at = _utc_iso()
        _finished_at = None
        _message = None
        _error_detail = None
        _log_excerpt = None
        _runner_expected = False
        _persist_from_globals()

    meta = {"profiles": list(profiles)}

    def _after_build() -> None:
        global _runner_expected
        with _lock:
            _runner_expected = True
            _persist_from_globals()

    def _worker() -> None:
        global _phase, _finished_at, _message, _error_detail, _log_excerpt, _runner_expected
        journal: list[str] = []
        try:
            run_compose_update(
                journal=journal,
                compose_job_id=jid,
                on_after_build_before_compose_up=_after_build,
            )
        except BaseException as e:
            err_s = str(e).strip() or type(e).__name__
            excerpt = _excerpt_from_journal(journal, err_s)
            with _lock:
                _runner_expected = False
                _phase = "failed"
                _finished_at = _utc_iso()
                _message = None
                _error_detail = err_s[:4000]
                _log_excerpt = excerpt or None
                _persist_from_globals()
            return

        excerpt = _excerpt_from_journal(journal, None)
        with _lock:
            _runner_expected = False
            _phase = "succeeded"
            _finished_at = _utc_iso()
            _message = (
                "Docker Compose finished (git pull if enabled, build --pull, up -d). "
                "Reload the app after containers restart."
            )
            _error_detail = None
            _log_excerpt = excerpt or None
            _persist_from_globals()
        try:
            from app.build_metadata import invalidate_live_compose_repo_head_cache

            invalidate_live_compose_repo_head_cache()
        except Exception:
            pass

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

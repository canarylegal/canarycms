"""Ephemeral paths for GUI Docker Compose updates (job status, compose-up markers).

All state lives under ``<compose project>/.canary/runtime`` — never under ``FILES_ROOT`` (user uploads).
"""

from __future__ import annotations

import os
from pathlib import Path

_RUNTIME_REL = Path(".canary") / "runtime"
JOB_STATE_FILENAME = "compose-job-state.json"


def compose_project_dir() -> Path:
    raw = (os.getenv("CANARY_COMPOSE_PROJECT_DIR") or "/canary-compose").strip()
    return Path(raw).resolve()


def compose_runtime_dir() -> Path:
    """Directory for compose job JSON state (created on demand)."""
    override = (os.getenv("CANARY_COMPOSE_RUNTIME_DIR") or "").strip()
    if override:
        root = Path(override).resolve()
    else:
        root = (compose_project_dir() / _RUNTIME_REL).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def compose_job_state_path() -> Path:
    return compose_runtime_dir() / JOB_STATE_FILENAME


def compose_up_marker_path(job_id: str) -> Path:
    return compose_runtime_dir() / f"compose-up-{job_id}.json"


def compose_up_marker_basename(job_id: str) -> str:
    return f"compose-up-{job_id}.json"


def resolve_compose_up_marker(job_id: str) -> Path | None:
    """Return marker file if present (primary runtime dir, then legacy locations)."""
    primary = compose_up_marker_path(job_id)
    if primary.is_file():
        return primary

    legacy_name = f".canary-compose-up-{job_id}.json"
    candidates: list[Path] = [compose_project_dir() / legacy_name]
    explicit = (os.getenv("CANARY_COMPOSE_HOST_PROJECT_DIR") or "").strip()
    if explicit:
        candidates.append(Path(explicit) / legacy_name)
    files_root = (os.getenv("FILES_ROOT") or "").strip()
    if files_root:
        candidates.append(Path(files_root) / legacy_name)
    for p in candidates:
        if p.is_file():
            return p
    return None


def legacy_compose_job_state_paths() -> list[Path]:
    """Old job-state mirrors (project root and FILES_ROOT) for one-time reconciliation."""
    name = ".canary-compose-job-state.json"
    out: list[Path] = [compose_project_dir() / name]
    explicit = (os.getenv("CANARY_COMPOSE_HOST_PROJECT_DIR") or "").strip()
    if explicit:
        p = Path(explicit) / name
        if p not in out:
            out.append(p)
    files_root = (os.getenv("FILES_ROOT") or "").strip()
    if files_root:
        p = Path(files_root) / name
        if p not in out:
            out.append(p)
    return out

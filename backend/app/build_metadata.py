"""Reported git SHA for /health (live mount when enabled) and update checks (image-baked when known)."""

from __future__ import annotations

import os
from pathlib import Path

_live_head_computed: bool = False
_live_head_value: str = ""


def invalidate_live_compose_repo_head_cache() -> None:
    """Forget cached ``git rev-parse HEAD`` from the compose project mount (call after compose updates)."""
    global _live_head_computed, _live_head_value
    _live_head_computed = False
    _live_head_value = ""


def _compose_project_dir_is_mounted() -> bool:
    raw = (os.getenv("CANARY_COMPOSE_PROJECT_DIR") or "").strip()
    if not raw:
        return False
    try:
        return Path(raw).resolve().is_dir()
    except OSError:
        return False


def _runtime_commit_from_compose_repo_enabled() -> bool:
    raw = (os.getenv("CANARY_RUNTIME_COMMIT_FROM_COMPOSE_REPO") or "auto").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return _compose_project_dir_is_mounted()


def _live_compose_repo_head() -> str | None:
    """Best-effort ``HEAD`` of the bind-mounted compose project (self-host). Cached per process."""
    global _live_head_computed, _live_head_value
    if _live_head_computed:
        return _live_head_value or None
    _live_head_computed = True
    _live_head_value = ""
    if not _runtime_commit_from_compose_repo_enabled():
        return None
    try:
        from app.local_compose_update import compose_project_git_head

        sha = compose_project_git_head()
    except Exception:
        sha = None
    if sha and len(sha) >= 7:
        _live_head_value = sha
        return sha
    return None


def _baked_build_commit() -> str:
    return (os.getenv("CANARY_BUILD_COMMIT") or "").strip() or "unknown"


def _commit_is_known(sha: str) -> bool:
    return bool(sha and sha != "unknown")


def effective_build_commit() -> str:
    """Return the commit string shown in ``/health``.

    Precedence: ``CANARY_BUILD_COMMIT_OVERRIDE`` → live ``git rev-parse HEAD`` on the compose project
    mount (when enabled) → ``CANARY_BUILD_COMMIT`` baked into the image.
    """
    override = (os.getenv("CANARY_BUILD_COMMIT_OVERRIDE") or "").strip()
    if override:
        return override
    live = _live_compose_repo_head()
    if live:
        return live
    return _baked_build_commit()


def effective_build_commit_for_update_check() -> str:
    """Commit compared to GitHub for Admin update checks (``/admin/deploy/update-check``).

    Precedence: ``CANARY_BUILD_COMMIT_OVERRIDE`` → image-baked ``CANARY_BUILD_COMMIT`` → live mount
    ``HEAD`` (only when baked is unknown) → ``unknown``. Prefers the baked SHA so a stale bind-mounted
    checkout cannot falsely mark the deployment behind GitHub after ``docker compose build``.
    """
    override = (os.getenv("CANARY_BUILD_COMMIT_OVERRIDE") or "").strip()
    if override:
        return override
    baked = _baked_build_commit()
    if _commit_is_known(baked):
        return baked
    live = _live_compose_repo_head()
    if live:
        return live
    return "unknown"

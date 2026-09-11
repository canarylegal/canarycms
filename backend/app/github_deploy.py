"""GitHub repository identity for Admin update checks (read-only API; OWNER / REPO / REF env vars)."""

from __future__ import annotations

import os

# Production default: compare this install to the latest GitHub *release* tip (not floating main).
# Set CANARY_GITHUB_DEPLOY_REF=main (or another branch/tag) only when you intentionally track that tip.
DEFAULT_GITHUB_DEPLOY_REF = "latest-release"

_LATEST_RELEASE_ALIASES = frozenset({"latest-release", "release", "latest"})


def configured_github_deploy_ref() -> str:
    """Raw REF from env (may be ``latest-release``)."""
    return (os.getenv("CANARY_GITHUB_DEPLOY_REF") or DEFAULT_GITHUB_DEPLOY_REF).strip() or DEFAULT_GITHUB_DEPLOY_REF


def is_latest_release_ref(ref: str) -> bool:
    return (ref or "").strip().lower() in _LATEST_RELEASE_ALIASES


def load_github_repo_for_api() -> tuple[str, str, str] | None:
    """Return ``(owner, repo, ref)`` for unauthenticated GitHub REST reads (public repos only).

    ``ref`` may be the sentinel ``latest-release``; callers that hit the commits API should resolve
    it via :func:`app.github_update_check.resolve_compare_ref` first.
    """
    owner = (os.getenv("CANARY_GITHUB_DEPLOY_OWNER") or "").strip()
    repo = (os.getenv("CANARY_GITHUB_DEPLOY_REPO") or "").strip()
    if not owner or not repo:
        return None
    return owner, repo, configured_github_deploy_ref()

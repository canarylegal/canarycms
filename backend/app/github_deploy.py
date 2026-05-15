"""GitHub repository identity for Admin update checks (read-only API; OWNER / REPO / REF env vars)."""

from __future__ import annotations

import os


def load_github_repo_for_api() -> tuple[str, str, str] | None:
    """Return ``(owner, repo, ref)`` for unauthenticated GitHub REST reads (public repos only)."""
    owner = (os.getenv("CANARY_GITHUB_DEPLOY_OWNER") or "").strip()
    repo = (os.getenv("CANARY_GITHUB_DEPLOY_REPO") or "").strip()
    if not owner or not repo:
        return None
    ref = (os.getenv("CANARY_GITHUB_DEPLOY_REF") or "main").strip() or "main"
    return owner, repo, ref

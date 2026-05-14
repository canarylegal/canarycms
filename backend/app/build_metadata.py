"""Reported git SHA for /health and update checks (optional runtime override)."""

from __future__ import annotations

import os


def effective_build_commit() -> str:
    """Return the commit string shown in /health and compared to GitHub for updates."""
    override = (os.getenv("CANARY_BUILD_COMMIT_OVERRIDE") or "").strip()
    if override:
        return override
    return (os.getenv("CANARY_BUILD_COMMIT") or "").strip()

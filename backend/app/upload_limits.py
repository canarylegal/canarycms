"""Shared upload size caps and safe inline Content-Disposition MIME allowlist."""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def max_upload_bytes() -> int:
    """Default 25 MiB — aligned with portal form uploads."""
    return _int_env("CANARY_UPLOAD_MAX_BYTES", 25 * 1024 * 1024)


# Browsers may safely render these inline; everything else forces attachment.
_SAFE_INLINE_MIME_PREFIXES = (
    "image/",
    "text/plain",
    "text/csv",
)
_SAFE_INLINE_MIME_EXACT = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/csv",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    }
)


def content_disposition_for_mime(mime_type: str | None, *, download: bool) -> str:
    if download:
        return "attachment"
    mt = (mime_type or "").strip().lower().split(";", 1)[0].strip()
    if mt in _SAFE_INLINE_MIME_EXACT:
        return "inline"
    if any(mt.startswith(p) for p in _SAFE_INLINE_MIME_PREFIXES):
        return "inline"
    return "attachment"

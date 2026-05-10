"""Normalize and validate user initials (unique label for filings, documents UI)."""

from __future__ import annotations

import re

_INITIALS_RE = re.compile(r"^[A-Z0-9._-]{1,12}$")


def normalize_initials(value: str) -> str:
    """Strip, uppercase, and validate initials; raises ``ValueError`` if invalid."""
    t = (value or "").strip().upper()
    if not _INITIALS_RE.fullmatch(t):
        raise ValueError(
            "Initials must be 1–12 characters and use only letters, numbers, dot, underscore, or hyphen."
        )
    return t

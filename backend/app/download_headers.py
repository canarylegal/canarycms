"""HTTP Content-Disposition helpers for file downloads."""

from __future__ import annotations

from urllib.parse import quote


def _latin1_safe_filename(filename: str) -> str:
    """Fallback filename for legacy ``filename=`` (must be Latin-1 encodable)."""
    normalized = filename.replace("\u2014", "-").replace("\u2013", "-")
    try:
        normalized.encode("latin-1")
        return normalized
    except UnicodeEncodeError:
        return normalized.encode("ascii", "replace").decode("ascii").replace("?", "_")


def attachment_content_disposition_headers(filename: str) -> dict[str, str]:
    """Build attachment headers that support Unicode display names in modern browsers."""
    fallback = _latin1_safe_filename(filename)
    if fallback == filename:
        return {"Content-Disposition": f'attachment; filename="{fallback}"'}
    encoded = quote(filename, safe="")
    return {
        "Content-Disposition": (
            f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'
        )
    }

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


def content_disposition_headers(filename: str, *, disposition: str = "attachment") -> dict[str, str]:
    """Build Content-Disposition headers that stay Latin-1 safe for Starlette/ASGI.

    Uses RFC 5987 ``filename*=`` when the display name needs characters outside Latin-1
    (e.g. em dash U+2014 in matter document titles).
    """
    kind = (disposition or "attachment").strip().lower()
    if kind not in ("attachment", "inline"):
        kind = "attachment"
    fallback = _latin1_safe_filename(filename)
    if fallback == filename:
        return {"Content-Disposition": f'{kind}; filename="{fallback}"'}
    encoded = quote(filename, safe="")
    return {
        "Content-Disposition": (
            f'{kind}; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'
        )
    }


def attachment_content_disposition_headers(filename: str) -> dict[str, str]:
    """Build attachment headers that support Unicode display names in modern browsers."""
    return content_disposition_headers(filename, disposition="attachment")

"""Validate and re-encode staff / firm signature image uploads (CL-02)."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ALLOWED_SIGNATURE_SUFFIX = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
ALLOWED_SIGNATURE_MIME = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
ALLOWED_SIGNATURE_FORMATS = frozenset({"PNG", "JPEG", "GIF", "WEBP"})
MAX_SIGNATURE_BYTES = 2 * 1024 * 1024
MAX_SIGNATURE_PIXELS = 4096


class SignatureImageError(ValueError):
    """Invalid signature image bytes or metadata."""


def assert_signature_filename_and_mime(filename: str, content_type: str | None) -> None:
    """Reject uploads whose declared name/type are not an allowed image format."""
    import mimetypes

    suf = Path(filename or "").suffix.lower()
    if suf not in ALLOWED_SIGNATURE_SUFFIX:
        raise SignatureImageError("Signature must be a PNG, JPEG, GIF, or WebP image.")
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime and mime not in ALLOWED_SIGNATURE_MIME:
        guess = mimetypes.guess_type(filename)[0]
        if guess not in ALLOWED_SIGNATURE_MIME:
            raise SignatureImageError("Signature must be a PNG, JPEG, GIF, or WebP image.")


def validate_and_reencode_signature_image(data: bytes) -> tuple[bytes, str]:
    """Decode image bytes, enforce limits, and re-encode as PNG.

    Returns ``(png_bytes, \"image/png\")``. Raises :class:`SignatureImageError` on failure.
    """
    if not data:
        raise SignatureImageError("Signature image is empty.")
    if len(data) > MAX_SIGNATURE_BYTES:
        raise SignatureImageError("Signature image must be 2 MB or smaller.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except UnidentifiedImageError as exc:
        raise SignatureImageError("Signature must be a valid PNG, JPEG, GIF, or WebP image.") from exc
    except OSError as exc:
        raise SignatureImageError("Signature must be a valid PNG, JPEG, GIF, or WebP image.") from exc

    fmt = (img.format or "").upper()
    if fmt not in ALLOWED_SIGNATURE_FORMATS:
        raise SignatureImageError("Signature must be a PNG, JPEG, GIF, or WebP image.")

    width, height = img.size
    if width < 1 or height < 1 or width > MAX_SIGNATURE_PIXELS or height > MAX_SIGNATURE_PIXELS:
        raise SignatureImageError(
            f"Signature image dimensions must be between 1 and {MAX_SIGNATURE_PIXELS} pixels."
        )

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        converted = img.convert("RGBA")
    else:
        converted = img.convert("RGB")

    out = io.BytesIO()
    converted.save(out, format="PNG", optimize=True)
    png = out.getvalue()
    if len(png) > MAX_SIGNATURE_BYTES:
        raise SignatureImageError("Signature image must be 2 MB or smaller after processing.")
    return png, "image/png"


def signature_storage_filename(original_filename: str) -> str:
    """Always persist re-encoded signatures as ``.png`` (stem from the upload name)."""
    stem = Path(original_filename or "signature").stem.strip() or "signature"
    # Avoid path components in the stored display name.
    safe = Path(stem).name.replace("\x00", "")[:80] or "signature"
    return f"{safe}.png"

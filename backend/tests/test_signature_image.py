"""Signature image content validation (CL-02)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.signature_image import (
    SignatureImageError,
    assert_signature_filename_and_mime,
    signature_storage_filename,
    validate_and_reencode_signature_image,
)


def _png_bytes(*, size: tuple[int, int] = (32, 16)) -> bytes:
    img = Image.new("RGB", size, color=(12, 34, 56))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_rejects_html_labelled_as_png() -> None:
    html = b"<!DOCTYPE html><html><body><script>/* marker */</script></body></html>"
    assert_signature_filename_and_mime("security-test.png", "image/png")
    with pytest.raises(SignatureImageError, match="valid PNG"):
        validate_and_reencode_signature_image(html)


def test_accepts_and_reencodes_real_png() -> None:
    raw = _png_bytes()
    out, mime = validate_and_reencode_signature_image(raw)
    assert mime == "image/png"
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(out))
    img.load()
    assert img.format == "PNG"
    assert img.size == (32, 16)


def test_rejects_oversized_dimensions() -> None:
    raw = _png_bytes(size=(5000, 10))
    with pytest.raises(SignatureImageError, match="dimensions"):
        validate_and_reencode_signature_image(raw)


def test_storage_filename_forces_png() -> None:
    assert signature_storage_filename("security-test.png") == "security-test.png"
    assert signature_storage_filename("My Sig.JPEG") == "My Sig.png"


def test_rejects_wrong_extension() -> None:
    with pytest.raises(SignatureImageError):
        assert_signature_filename_and_mime("note.html", "text/html")

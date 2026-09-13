"""Download Content-Disposition header encoding."""

from __future__ import annotations

from starlette.responses import StreamingResponse
from io import BytesIO

from app.download_headers import (
    attachment_content_disposition_headers,
    content_disposition_headers,
)


def test_attachment_headers_support_em_dash_filename() -> None:
    headers = attachment_content_disposition_headers("Client account reconcile report — 2026-06.docx")
    response = StreamingResponse(BytesIO(b"x"), headers=headers)
    # Must not raise when Starlette encodes headers for ASGI.
    encoded = list(response.raw_headers)
    disp = next(v.decode("latin-1") for k, v in encoded if k.decode("latin-1").lower() == "content-disposition")
    assert "filename=\"Client account reconcile report - 2026-06.docx\"" in disp
    assert "filename*=UTF-8" in disp


def test_inline_headers_support_em_dash_filename() -> None:
    headers = content_disposition_headers("Agreement — to sign.pdf", disposition="inline")
    response = StreamingResponse(BytesIO(b"%PDF"), media_type="application/pdf", headers=headers)
    encoded = list(response.raw_headers)
    disp = next(v.decode("latin-1") for k, v in encoded if k.decode("latin-1").lower() == "content-disposition")
    assert disp.startswith("inline;")
    assert "filename=\"Agreement - to sign.pdf\"" in disp
    assert "filename*=UTF-8" in disp

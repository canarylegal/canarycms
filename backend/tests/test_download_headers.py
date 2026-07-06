"""Download Content-Disposition header encoding."""

from __future__ import annotations

from starlette.responses import StreamingResponse
from io import BytesIO

from app.download_headers import attachment_content_disposition_headers


def test_attachment_headers_support_em_dash_filename() -> None:
    headers = attachment_content_disposition_headers("Client account reconcile report — 2026-06.docx")
    response = StreamingResponse(BytesIO(b"x"), headers=headers)
    # Must not raise when Starlette encodes headers for ASGI.
    encoded = list(response.raw_headers)
    disp = next(v.decode("latin-1") for k, v in encoded if k.decode("latin-1").lower() == "content-disposition")
    assert "filename=\"Client account reconcile report - 2026-06.docx\"" in disp
    assert "filename*=UTF-8" in disp

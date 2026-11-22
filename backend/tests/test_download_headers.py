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

import pytest
from urllib.parse import unquote

@pytest.mark.parametrize('name',['evil"; x="value.pdf','bad\r\nX-Evil: injected.pdf','bad\x00\x1f\x7f\x85.pdf','../path\\name.pdf','你好"\r\n.pdf','\r\n','line\u2028break\u2029.pdf'])
@pytest.mark.parametrize('kind',['inline','attachment'])
def test_download_names_cannot_break_header_syntax(name,kind):
    value=content_disposition_headers(name,disposition=kind)['Content-Disposition']
    assert not any(ord(c)<32 or 127<=ord(c)<=159 for c in value)
    assert value.count('"')==2
    fallback=value.split('filename="',1)[1].split('"',1)[0]
    assert fallback and '\\' not in fallback and '/' not in fallback
    if "filename*=UTF-8''" in value:
        decoded=unquote(value.split("filename*=UTF-8''",1)[1])
        assert '"' not in decoded and '\r' not in decoded and '\n' not in decoded
    StreamingResponse(BytesIO(b'%PDF-synthetic'),headers={'Content-Disposition':value})

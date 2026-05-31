"""Digital letterhead image / media package merging."""

import base64
import io
import zipfile

from docx import Document
from docx.shared import Inches

from app.docx_util import apply_digital_letterhead_headers_footers

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _letterhead_with_header_image() -> bytes:
    doc = Document()
    doc.add_paragraph("")
    doc.sections[0].header.paragraphs[0].add_run().add_picture(
        io.BytesIO(_PNG_1PX), width=Inches(1)
    )
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _blank_precedent() -> bytes:
    doc = Document()
    doc.add_paragraph("Letter body")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_letterhead_merge_copies_media_and_header_rels() -> None:
    merged = apply_digital_letterhead_headers_footers(_blank_precedent(), _letterhead_with_header_image())
    with zipfile.ZipFile(io.BytesIO(merged)) as z:
        assert "word/media/image1.png" in z.namelist()
        rels = z.read("word/_rels/header1.xml.rels").decode()
        assert "media/image1.png" in rels
        assert 'r:embed="rId1"' in z.read("word/header1.xml").decode()


def test_letterhead_merge_content_types_includes_png() -> None:
    merged = apply_digital_letterhead_headers_footers(_blank_precedent(), _letterhead_with_header_image())
    with zipfile.ZipFile(io.BytesIO(merged)) as z:
        ct = z.read("[Content_Types].xml").decode()
        assert 'Extension="png"' in ct

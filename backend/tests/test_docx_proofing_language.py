"""Unit tests for en-GB document language normalisation in .docx OOXML."""

from __future__ import annotations

import io
import zipfile

from app.docx_util import (
    ensure_docx_proofing_language_en_gb_bytes,
    finalize_stored_docx_bytes,
    normalize_onlyoffice_persisted_docx_bytes,
)

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _minimal_docx(*, word_parts: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/settings.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            "</Types>",
        )
        for name, xml in word_parts.items():
            zout.writestr(name, xml)
    return buf.getvalue()


def _read_part(docx_bytes: bytes, part: str) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        return zin.read(part).decode("utf-8")


def test_patches_theme_font_lang_and_run_lang_from_en_us_to_en_gb() -> None:
    settings = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{_W_NS}">'
        f'<w:themeFontLang w:val="en-US" w:eastAsia="en-US" w:bidi="en-US"/>'
        "</w:settings>"
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W_NS}">'
        "<w:body>"
        "<w:p><w:r><w:rPr><w:lang w:val=\"en-US\"/></w:rPr><w:t>Hello</w:t></w:r></w:p>"
        "</w:body>"
        "</w:document>"
    )
    src = _minimal_docx(word_parts={"word/settings.xml": settings, "word/document.xml": document})

    out = ensure_docx_proofing_language_en_gb_bytes(src)

    settings_out = _read_part(out, "word/settings.xml")
    document_out = _read_part(out, "word/document.xml")
    assert "en-GB" in settings_out
    assert "en-US" not in settings_out
    assert "en-GB" in document_out
    assert "en-US" not in document_out


def test_normalize_onlyoffice_persisted_docx_strips_orphan_comment_rels() -> None:
    import tempfile
    from pathlib import Path

    from app.docx_util import write_blank_docx

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "blank.docx"
        write_blank_docx(p)
        src = p.read_bytes()

    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src), "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            zout.writestr(info, zin.read(info.filename))
        zout.writestr(
            "word/_rels/comments.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
        )
    broken = buf.getvalue()

    fixed = normalize_onlyoffice_persisted_docx_bytes(broken, filename="quote.docx")
    with zipfile.ZipFile(io.BytesIO(fixed), "r") as zf:
        assert "word/_rels/comments.xml.rels" not in zf.namelist()


def test_lang_patch_does_not_bloat_styles_xml() -> None:
    """Regression: ElementTree rewrite of styles.xml broke ONLYOFFICE open on quote compose."""
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{_W_NS}">'
        f'<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/>'
        f'<w:rPr><w:lang w:val="en-US"/></w:rPr></w:style>'
        + "".join(
            f'<w:style w:type="character" w:styleId="s{i}"><w:name w:val="S{i}"/></w:style>'
            for i in range(200)
        )
        + "</w:styles>"
    )
    src = _minimal_docx(word_parts={"word/styles.xml": styles, "word/settings.xml": (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{_W_NS}"><w:themeFontLang w:val="en-US"/></w:settings>'
    )})
    before = len(_read_part(src, "word/styles.xml"))
    out = ensure_docx_proofing_language_en_gb_bytes(src)
    after = len(_read_part(out, "word/styles.xml"))
    assert after <= before + 400  # docDefaults inject only
    assert "en-US" not in _read_part(out, "word/styles.xml")
    assert "en-GB" in _read_part(out, "word/settings.xml")


def test_finalize_stored_docx_bytes_only_applies_to_docx() -> None:
    settings = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{_W_NS}">'
        f'<w:themeFontLang w:val="en-US"/>'
        "</w:settings>"
    )
    src = _minimal_docx(word_parts={"word/settings.xml": settings})
    out = finalize_stored_docx_bytes(src, filename="letter.docx")
    assert "en-US" not in _read_part(out, "word/settings.xml")

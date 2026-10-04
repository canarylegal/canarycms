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


def _letterhead_with_body_image() -> bytes:
    doc = Document()
    doc.add_paragraph().add_run().add_picture(io.BytesIO(_PNG_1PX), width=Inches(1))
    doc.add_paragraph("")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_letterhead_merge_prepends_body_masthead_image() -> None:
    merged = apply_digital_letterhead_headers_footers(_blank_precedent(), _letterhead_with_body_image())
    with zipfile.ZipFile(io.BytesIO(merged)) as z:
        assert "word/media/image1.png" in z.namelist()
        doc_xml = z.read("word/document.xml").decode()
        assert "Letter body" in doc_xml
        assert "drawing" in doc_xml or "blip" in doc_xml
        rels = z.read("word/_rels/document.xml.rels").decode()
        assert "media/image1.png" in rels


def _letterhead_with_first_page_footer() -> bytes:
    """Mimics Ashbourne and Finch-style letterheads: firm lines on the first-page footer only."""
    doc = Document()
    doc.add_paragraph("")
    sec = doc.sections[0]
    sec.different_first_page_header_footer = True
    sec.first_page_footer.paragraphs[0].add_run("49 Bell Street, Sawbridgeworth")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_letterhead_merge_copies_first_page_footer() -> None:
    merged = apply_digital_letterhead_headers_footers(_blank_precedent(), _letterhead_with_first_page_footer())
    out = Document(io.BytesIO(merged))
    sec = out.sections[0]
    assert sec.different_first_page_header_footer is True
    footer_text = "\n".join(p.text for p in sec.first_page_footer.paragraphs)
    assert "Bell Street" in footer_text


def _letterhead_with_compat_mode(*, mode: str) -> bytes:
    import xml.etree.ElementTree as ET

    doc = Document()
    doc.add_paragraph("")
    sec = doc.sections[0]
    sec.different_first_page_header_footer = True
    sec.first_page_footer.paragraphs[0].add_run("Footer line one")
    buf = io.BytesIO()
    doc.save(buf)
    parts: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(buf.getvalue()), "r") as zin:
        for info in zin.infolist():
            parts[info.filename] = zin.read(info.filename)
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = ET.fromstring(parts["word/settings.xml"])
    compat = root.find(f"{{{W}}}compat")
    if compat is None:
        compat = ET.SubElement(root, f"{{{W}}}compat")
    for child in list(compat):
        compat.remove(child)
    cs = ET.SubElement(compat, f"{{{W}}}compatSetting")
    cs.set(f"{{{W}}}name", "compatibilityMode")
    cs.set(f"{{{W}}}val", mode)
    parts["word/settings.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    return out.getvalue()


def _compat_mode_from_docx(data: bytes) -> str | None:
    import xml.etree.ElementTree as ET

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/settings.xml"))
    compat = root.find(f"{{{W}}}compat")
    if compat is None:
        return None
    for cs in compat.findall(f"{{{W}}}compatSetting"):
        if cs.get(f"{{{W}}}name") == "compatibilityMode":
            return cs.get(f"{{{W}}}val")
    return None


def test_letterhead_merge_applies_letterhead_compatibility_mode() -> None:
    """Precedent scaffolds often use a newer Word compat mode than the uploaded letterhead."""
    lh = _letterhead_with_compat_mode(mode="11")
    prec = _letterhead_with_compat_mode(mode="14")
    merged = apply_digital_letterhead_headers_footers(prec, lh)
    assert _compat_mode_from_docx(merged) == "11"


def test_letterhead_merge_tightens_footer_paragraph_spacing() -> None:
    lh = _letterhead_with_first_page_footer()
    prec = _blank_precedent()
    merged = apply_digital_letterhead_headers_footers(prec, lh)
    with zipfile.ZipFile(io.BytesIO(merged)) as z:
        footer_name = next(
            n for n in z.namelist() if n.startswith("word/footer") and b"Bell Street" in z.read(n)
        )
        footer_xml = z.read(footer_name).decode()
    assert 'after="0"' in footer_xml
    assert 'line="240"' in footer_xml


def _letterhead_with_loose_doc_defaults() -> bytes:
    """Letterhead whose styles.xml uses Word's common loose body spacing defaults."""
    import re

    doc = Document()
    doc.add_paragraph("")
    buf = io.BytesIO()
    doc.save(buf)
    raw = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zin:
        parts = {name: zin.read(name) for name in zin.namelist()}
    styles = parts["word/styles.xml"].decode("utf-8")
    loose = (
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        '<w:lang w:val="en-GB"/>'
        "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
        '<w:spacing w:after="200" w:line="276" w:lineRule="auto"/>'
        "</w:pPr></w:pPrDefault></w:docDefaults>"
    )
    if "<w:docDefaults>" in styles:
        styles = re.sub(r"<w:docDefaults>.*?</w:docDefaults>", loose, styles, count=1, flags=re.S)
    else:
        styles = re.sub(r"(<w:styles\b[^>]*>)", r"\1" + loose, styles, count=1)
    parts["word/styles.xml"] = styles.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    return out.getvalue()


def test_pin_empty_body_paragraph_spacing_content_keeps_docdefaults_after() -> None:
    from app.docx_util.letterhead import pin_empty_body_paragraph_spacing
    from docx.oxml.ns import qn

    doc = Document()
    p = doc.add_paragraph("Hello")
    p_pr = p._p.get_or_add_pPr()
    # Mimic sale-style body precedents: empty <w:spacing/> with no after/before.
    p_pr.append(p._p.makeelement(qn("w:spacing"), {}))
    empty = doc.add_paragraph("")
    empty._p.get_or_add_pPr().append(empty._p.makeelement(qn("w:spacing"), {}))
    buf = io.BytesIO()
    doc.save(buf)
    pinned = pin_empty_body_paragraph_spacing(buf.getvalue())
    out = Document(io.BytesIO(pinned))
    content_sp = out.paragraphs[0]._p.find(qn("w:pPr")).find(qn("w:spacing"))
    empty_sp = out.paragraphs[1]._p.find(qn("w:pPr")).find(qn("w:spacing"))
    assert content_sp is not None
    # Content gets explicit docDefaults after (Dear→body gap); blank spacers stay after=0.
    assert content_sp.get(qn("w:after")) == "200"
    assert content_sp.get(qn("w:before")) == "0"
    assert empty_sp is not None
    assert empty_sp.get(qn("w:after")) == "0"
    assert empty_sp.get(qn("w:before")) == "0"


def test_letterhead_merge_keeps_precedent_paragraph_spacing() -> None:
    """Letterhead fonts apply, but body paragraph spacing stays with the letter precedent."""
    import re

    # Precedent with explicit loose body spacing (matches BLANK_LETTER / Word defaults).
    prec_doc = Document()
    prec_doc.add_paragraph("Letter body")
    buf = io.BytesIO()
    prec_doc.save(buf)
    prec_raw = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(prec_raw), "r") as zin:
        parts = {name: zin.read(name) for name in zin.namelist()}
    styles = parts["word/styles.xml"].decode("utf-8")
    prec_defaults = (
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        '<w:lang w:val="en-US"/>'
        "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
        '<w:spacing w:after="200" w:line="276" w:lineRule="auto"/>'
        "</w:pPr></w:pPrDefault></w:docDefaults>"
    )
    if "<w:docDefaults>" in styles:
        styles = re.sub(r"<w:docDefaults>.*?</w:docDefaults>", prec_defaults, styles, count=1, flags=re.S)
    else:
        styles = re.sub(r"(<w:styles\b[^>]*>)", r"\1" + prec_defaults, styles, count=1)
    parts["word/styles.xml"] = styles.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    prec_bytes = out.getvalue()

    merged = apply_digital_letterhead_headers_footers(prec_bytes, _letterhead_with_loose_doc_defaults())
    with zipfile.ZipFile(io.BytesIO(merged)) as z:
        merged_styles = z.read("word/styles.xml").decode("utf-8")
    match = re.search(r"<w:docDefaults>.*?</w:docDefaults>", merged_styles, flags=re.S)
    assert match is not None
    defaults = match.group(0)
    # Precedent paragraph spacing preserved.
    assert 'after="200"' in defaults
    assert 'line="276"' in defaults
    # Letterhead run language applied (en-GB from helper), not the precedent's en-US alone.
    assert 'w:val="en-GB"' in defaults or 'val="en-GB"' in defaults

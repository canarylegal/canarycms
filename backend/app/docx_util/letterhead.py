"""Digital letterhead masthead / header-footer splice helpers."""
from __future__ import annotations

import re
from typing import Any

from .proofing import _DOC_DEFAULTS_BLOCK_RE, _STYLES_OPEN_RE
from .quote_table import PRECEDENT_BODY_MARKER

def _copy_section_page_geometry(src_section: Any, tgt_section: Any) -> None:
    """Apply letterhead section ``w:pgSz`` / ``w:pgMar`` onto the precedent section.

    Header/footer blocks alone do not define vertical padding: the section's page margins and
    ``header`` / ``footer`` distances (python-docx: ``header_distance``, ``footer_distance``)
    reserve space for header/footer content above and below the body. Without copying these,
    the precedent's geometry wins and letterhead spacing set in Word disappears in compose
    (especially noticeable in ONLYOFFICE).
    """

    for attr in (
        "page_width",
        "page_height",
        "orientation",
        "left_margin",
        "right_margin",
        "top_margin",
        "bottom_margin",
        "header_distance",
        "footer_distance",
        "gutter",
    ):
        try:
            val = getattr(src_section, attr)
        except AttributeError:
            continue
        if val is None:
            continue
        setattr(tgt_section, attr, val)

_LETTER_SCAFFOLD_PREFIX_TEXT_RE = (
    re.compile(r"^\s*Re:\s*\[MATTER_DESCRIPTION\]\s*$", re.I),
    re.compile(r"^\s*\[SOLICITOR_OUR_CLIENT_LINE\]\s*$", re.I),
    re.compile(r"^\s*\[SOLICITOR_YOUR_CLIENT_LINE\]\s*$", re.I),
    # Body precedents sometimes still include a full letter shell — strip it so BLANK_LETTER owns spacing.
    re.compile(
        r"^\s*\[(?:CONTACT_ORG_AND_ADDRESS_BLOCK|ORG_AND_ADDRESS_BLOCK|PRIMARY_CLIENT_NAME|"
        r"CONTACT_ORG_LINES|ORG_LINES|CONTACT_ADDRESS_BLOCK|ADDRESS_BLOCK)\]\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*\[TITLE\](?:\s*\[(?:FIRST_INITIAL|MIDDLE_INITIAL|LAST_NAME|TITLE_\d|"
        r"FIRST_INITIAL_\d|MIDDLE_INITIAL_\d|LAST_NAME_\d)\])*"
        r"(?:\s*\[(?:ORG_AND_ADDRESS_BLOCK|CONTACT_ORG_AND_ADDRESS_BLOCK)\])?\s*$",
        re.I,
    ),
    re.compile(r"^\s*\[DATE\]\s*$", re.I),
    re.compile(r"^\s*Your\s+Ref\s*:", re.I),
    re.compile(r"^\s*Our\s+Ref\s*:", re.I),
    re.compile(r"^\s*Dear\b", re.I),
    re.compile(r"^\s*\[(?:CONTACT_LETTER_DEAR|PRIMARY_CLIENT_LETTER_DEAR|CLIENT_\d_LETTER_DEAR)\]\s*$", re.I),
    # Hard-coded dates left from sterilised Word mail-merge shells.
    re.compile(
        r"^\s*\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+20\d{2}\s*$",
        re.I,
    ),
    # Leftover Word MERGEFIELD address/date lines.
    re.compile(r"^\s*MERGEFIELD\b", re.I),
    re.compile(r"^\s*\[?\s*MERGEFIELD\b", re.I),
)

_LETTER_SCAFFOLD_RE_LINE_RE = re.compile(r"^\s*Re\s*:", re.I)
_BLANK_LETTER_SIGN_OFF_RE = re.compile(
    r"^\s*(?:Yours\s+(?:sincerely|faithfully),?|\[CONTACT_LETTER_SIGN_OFF\]|"
    r"\[FEE_EARNER_SIGNATURE\]|\[FEE_EARNER\]|\[FEE_EARNER_JOB_TITLE\]|\[FIRM_TRADING_NAME\])\s*$",
    re.I,
)


def precedent_is_standalone_letter(src_bytes: bytes) -> bool:
    """True when a letter precedent already includes its own shell (date, refs, etc.)."""
    # Prefer uncompressed document.xml — raw ZIP bytes often hide tokens inside deflate streams.
    try:
        import zipfile
        import io

        with zipfile.ZipFile(io.BytesIO(src_bytes)) as zf:
            try:
                xml = zf.read("word/document.xml")
            except KeyError:
                xml = b""
        haystack = xml or src_bytes
    except Exception:
        haystack = src_bytes
    return b"[DATE]" in haystack and PRECEDENT_BODY_MARKER.encode() not in haystack


def _strip_letter_scaffold_prefix_from_body_elements(
    src_elements: list[Any],
    *,
    p_tag: str,
    t_tag: str,
) -> list[Any]:
    elements = list(src_elements)
    while elements:
        if elements[0].tag != p_tag:
            break
        text = "".join((t.text or "") for t in elements[0].iter(t_tag)).strip()
        if not text:
            elements.pop(0)
            continue
        if any(pat.match(text) for pat in _LETTER_SCAFFOLD_PREFIX_TEXT_RE):
            elements.pop(0)
            continue
        break
    return elements


def _body_elements_start_with_re_line(elements: list[Any], *, p_tag: str, t_tag: str) -> bool:
    for el in elements:
        if el.tag != p_tag:
            continue
        text = "".join((t.text or "") for t in el.iter(t_tag)).strip()
        if not text:
            continue
        return bool(_LETTER_SCAFFOLD_RE_LINE_RE.match(text))
    return False


def _body_elements_include_sign_off(elements: list[Any], *, p_tag: str, t_tag: str) -> bool:
    for el in elements:
        if el.tag != p_tag:
            continue
        text = "".join((t.text or "") for t in el.iter(t_tag)).strip()
        low = text.lower()
        if _BLANK_LETTER_SIGN_OFF_RE.match(text) and (
            "sincerely" in low or "faithfully" in low or "letter_sign_off" in low
        ):
            return True
    return False


def _remove_blank_letter_scaffold_subject_lines(base_body: Any, *, p_tag: str, t_tag: str) -> None:
    """Drop BLANK_LETTER ``Re:`` / solicitor lines when the spliced body already supplies a subject."""
    to_remove: list[Any] = []
    for el in list(base_body):
        if el.tag != p_tag:
            continue
        text = "".join((t.text or "") for t in el.iter(t_tag)).strip()
        if any(
            pat.match(text)
            for pat in (
                re.compile(r"^\s*Re:\s*\[MATTER_DESCRIPTION\]\s*$", re.I),
                re.compile(r"^\s*\[SOLICITOR_OUR_CLIENT_LINE\]\s*$", re.I),
                re.compile(r"^\s*\[SOLICITOR_YOUR_CLIENT_LINE\]\s*$", re.I),
            )
        ):
            to_remove.append(el)
    for el in to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)


def _remove_blank_letter_trailing_sign_off(base_body: Any, *, p_tag: str, t_tag: str) -> None:
    """Drop BLANK_LETTER signature block when the spliced body already includes one."""
    children = list(base_body)
    # Walk from end (before sectPr) removing contiguous sign-off / empty paras.
    from docx.oxml.ns import qn

    sect_pr_tag = qn("w:sectPr")
    i = len(children) - 1
    while i >= 0 and children[i].tag == sect_pr_tag:
        i -= 1
    removed_any = False
    while i >= 0:
        el = children[i]
        if el.tag != p_tag:
            break
        text = "".join((t.text or "") for t in el.iter(t_tag)).strip()
        if not text or _BLANK_LETTER_SIGN_OFF_RE.match(text):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
            removed_any = True
            i -= 1
            continue
        break
    # Only empty trailing cleanup is fine; if we never saw a sign-off token, put nothing back.
    del removed_any


def _paragraph_element_plain_text(el: Any, *, t_tag: str) -> str:
    return "".join((t.text or "") for t in el.iter(t_tag)).strip()


def _is_sign_off_opening_text(text: str) -> bool:
    return bool(re.match(r"^\s*Yours\s+(?:sincerely|faithfully)\s*,?\s*$", text or "", re.I))


def _collapse_letter_spacer_paragraphs(body: Any, *, p_tag: str, t_tag: str) -> None:
    """Remove empty paragraphs that only exist as double-spacing between content.

    Sterilised Word letters often insert a blank para between every block. Combined with
    BLANK_LETTER ``after=200`` defaults that parks a bus between lines. Keep at most one
    blank immediately after ``Yours sincerely/faithfully`` so the signature still has air.
    """
    from docx.oxml.ns import qn

    sect_pr_tag = qn("w:sectPr")
    children = [el for el in list(body) if el.tag != sect_pr_tag]
    to_remove: list[Any] = []
    i = 0
    while i < len(children):
        el = children[i]
        if el.tag != p_tag:
            i += 1
            continue
        text = _paragraph_element_plain_text(el, t_tag=t_tag)
        if text:
            i += 1
            continue
        # Empty paragraph — decide whether to keep one after a Yours… line.
        prev_text = ""
        for j in range(i - 1, -1, -1):
            if children[j].tag != p_tag:
                continue
            prev_text = _paragraph_element_plain_text(children[j], t_tag=t_tag)
            if prev_text:
                break
        keep = _is_sign_off_opening_text(prev_text)
        # Collapse a run of empties to a single kept blank (or none).
        run_end = i
        while run_end + 1 < len(children):
            nxt = children[run_end + 1]
            if nxt.tag != p_tag:
                break
            if _paragraph_element_plain_text(nxt, t_tag=t_tag):
                break
            run_end += 1
        if keep:
            for k in range(i + 1, run_end + 1):
                to_remove.append(children[k])
        else:
            for k in range(i, run_end + 1):
                to_remove.append(children[k])
        i = run_end + 1
    for el in to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)


def splice_precedent_into_blank_letter(blank_letter_bytes: bytes, precedent_bytes: bytes) -> bytes:
    """Use BLANK_LETTER as the scaffold and inject the chosen precedent's body content into it.

    BLANK_LETTER provides the letter shell: headers, footers, page geometry, and the body merge-code
    scaffold (e.g. recipient address block, date, ``Your Ref`` / ``Our Ref``, salutation, ``Re:``).
    The chosen precedent contributes only its body block elements (paragraphs + tables); its own
    headers/footers/page geometry and any trailing ``w:sectPr`` are discarded.

    Insertion point:
      - If BLANK_LETTER contains a paragraph whose visible text includes ``[PRECEDENT_BODY]``,
        that paragraph is **replaced** with the precedent body elements. This is the recommended
        way to position the precedent body precisely (e.g. between salutation and a static signature
        block that lives in BLANK_LETTER).
      - Otherwise the precedent body is appended at the **end of BLANK_LETTER's body**, just before
        the trailing ``w:sectPr`` page-setup element. For a typical scaffold that ends with
        ``Re: …``, this puts the chosen precedent's content immediately after the subject line.

    Leading ``Re:`` / solicitor client lines duplicated in the precedent file (for upload review) are
    stripped before insertion when the blank letter scaffold already supplies them.

    Caveats:
      - Style references in the precedent body (e.g. ``Heading 1``) resolve against BLANK_LETTER's
        ``word/styles.xml``. Common built-in styles work; precedent-only custom styles fall back to
        defaults.
      - Numbering definitions and embedded images in the precedent body may not transfer (numbered
        lists can lose their numbering format; image rels may dangle). For anything that must always
        render correctly, put it in BLANK_LETTER.
      - Merge-code substitution must run on the combined result (caller's responsibility).
    """
    import io
    from copy import deepcopy

    from docx import Document

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    p_tag = f"{{{W}}}p"
    tbl_tag = f"{{{W}}}tbl"
    t_tag = f"{{{W}}}t"
    sect_pr_tag = f"{{{W}}}sectPr"

    base = Document(io.BytesIO(blank_letter_bytes))
    src = Document(io.BytesIO(precedent_bytes))

    base_body = base.element.body
    src_body = src.element.body

    src_elements = [deepcopy(el) for el in src_body if el.tag in (p_tag, tbl_tag)]
    src_elements = _strip_letter_scaffold_prefix_from_body_elements(
        src_elements,
        p_tag=p_tag,
        t_tag=t_tag,
    )
    if not src_elements:
        out_empty = io.BytesIO()
        base.save(out_empty)
        return out_empty.getvalue()

    if _body_elements_start_with_re_line(src_elements, p_tag=p_tag, t_tag=t_tag):
        _remove_blank_letter_scaffold_subject_lines(base_body, p_tag=p_tag, t_tag=t_tag)
    if _body_elements_include_sign_off(src_elements, p_tag=p_tag, t_tag=t_tag):
        _remove_blank_letter_trailing_sign_off(base_body, p_tag=p_tag, t_tag=t_tag)

    marker_para = None
    for el in base_body:
        if el.tag != p_tag:
            continue
        text = "".join((t.text or "") for t in el.iter(t_tag))
        if PRECEDENT_BODY_MARKER in text:
            marker_para = el
            break

    if marker_para is not None:
        parent = marker_para.getparent()
        idx = list(parent).index(marker_para)
        for offset, new_el in enumerate(src_elements):
            parent.insert(idx + offset, new_el)
        parent.remove(marker_para)
    else:
        sect_pr = next((el for el in base_body if el.tag == sect_pr_tag), None)
        if sect_pr is not None:
            idx = list(base_body).index(sect_pr)
            for offset, new_el in enumerate(src_elements):
                base_body.insert(idx + offset, new_el)
        else:
            for new_el in src_elements:
                base_body.append(new_el)

    _collapse_letter_spacer_paragraphs(base_body, p_tag=p_tag, t_tag=t_tag)

    out = io.BytesIO()
    base.save(out)
    return out.getvalue()


_OD_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_HF_PART_RE = re.compile(r"^word/(header|footer)\d+\.xml$")
_REL_ID_REF_RE = re.compile(r'(?:r:embed|r:id|r:link)="([^"]+)"')
_LETTERHEAD_DATE_LINE_RE = re.compile(
    r"^\s*\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\s*$",
    re.I,
)
_LETTERHEAD_RE_LINE_RE = re.compile(r"^\s*re\s*:", re.I)
_LETTERHEAD_SUBJECT_LINE_RE = re.compile(
    r"^\s*(your\s+(purchase|sale)|purchase\s+of|sale\s+of|your\s+remortgage|re:\s*)",
    re.I,
)
_LETTERHEAD_ADDRESS_PLACEHOLDER_RE = re.compile(
    r"(solicitor.?s?\s+address|buyer.?s\s+solicitors?\s+address|seller.?s\s+solicitor)",
    re.I,
)


def _ooxml_element_plain_text(el: Any) -> str:
    from docx.oxml.ns import qn

    t_tag = qn("w:t")
    return "".join((t.text or "") for t in el.iter(t_tag)).strip()


def _ooxml_element_has_image(el: Any) -> bool:
    xml = el.xml if hasattr(el, "xml") else ""
    return "imagedata" in xml or "}drawing" in xml or "v:imagedata" in xml


def _is_letterhead_masthead_boundary_element(el: Any) -> bool:
    """True when a body paragraph/table starts letter content (not masthead branding)."""
    xml = el.xml if hasattr(el, "xml") else ""
    if "MERGEFIELD" in xml or "FORMTEXT" in xml:
        return True
    text = _ooxml_element_plain_text(el)
    if not text:
        return False
    if _LETTERHEAD_DATE_LINE_RE.match(text):
        return True
    low = text.lower()
    if low.startswith("your ref") or low.startswith("our ref"):
        return True
    if low.startswith("dear "):
        return True
    if _LETTERHEAD_RE_LINE_RE.match(text) or _LETTERHEAD_SUBJECT_LINE_RE.match(text):
        return True
    if _LETTERHEAD_ADDRESS_PLACEHOLDER_RE.search(text):
        return True
    return False


def extract_letterhead_body_masthead_elements(body_element: Any) -> list[Any]:
    """Body paragraphs/tables before the letter content block (e.g. floating logo masthead)."""
    from docx.oxml.ns import qn

    p_tag = qn("w:p")
    tbl_tag = qn("w:tbl")
    masthead: list[Any] = []
    for child in body_element:
        if child.tag not in (p_tag, tbl_tag):
            continue
        if masthead and _is_letterhead_masthead_boundary_element(child):
            break
        if not masthead and _is_letterhead_masthead_boundary_element(child):
            break
        masthead.append(child)
    return masthead


def extract_letterhead_body_masthead_elements_for_document(doc: Any) -> list[Any]:
    return extract_letterhead_body_masthead_elements(doc.element.body)


def _read_docx_zip_parts(raw: bytes) -> dict[str, bytes]:
    import io
    import zipfile

    parts: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        for name in zf.namelist():
            parts[name] = zf.read(name)
    return parts


def _write_docx_zip_parts(parts: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    return buf.getvalue()


def _ooxml_rels_part_path(part_path: str) -> str:
    folder, name = part_path.rsplit("/", 1)
    return f"{folder}/_rels/{name}.rels"


def _parse_ooxml_relationships(rels_bytes: bytes) -> list[tuple[str, str, str]]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(rels_bytes)
    rels: list[tuple[str, str, str]] = []
    for el in root:
        if el.tag.rsplit("}", 1)[-1] != "Relationship":
            continue
        rels.append((el.get("Id") or "", el.get("Type") or "", el.get("Target") or ""))
    return rels


def _resolve_word_part_path(target: str) -> str:
    path = target.lstrip("/")
    if not path.startswith("word/"):
        path = f"word/{path}"
    return path


def _hf_parts_by_reference(parts: dict[str, bytes]) -> dict[tuple[str, str], str]:
    """Map ``(header|footer, default|first|even)`` → ``word/headerN.xml`` / ``word/footerN.xml`` path."""
    import xml.etree.ElementTree as ET

    result: dict[tuple[str, str], str] = {}
    doc_rels_path = "word/_rels/document.xml.rels"
    if "word/document.xml" not in parts:
        return result

    rid_to_target: dict[str, str] = {}
    if doc_rels_path in parts:
        for rid, _typ, target in _parse_ooxml_relationships(parts[doc_rels_path]):
            rid_to_target[rid] = _resolve_word_part_path(target)

    try:
        root = ET.fromstring(parts["word/document.xml"])
    except ET.ParseError:
        return result

    for sect in root.iter(f"{{{_W_NS}}}sectPr"):
        for tag, kind in (("headerReference", "header"), ("footerReference", "footer")):
            for el in sect.iter(f"{{{_W_NS}}}{tag}"):
                ref_type = el.get(f"{{{_W_NS}}}type") or "default"
                rid = el.get(f"{{{_OD_REL_NS}}}id")
                if rid and rid in rid_to_target:
                    result[(kind, ref_type)] = rid_to_target[rid]
        break

    return result


def _letterhead_default_hf_rels_paths(lh_parts: dict[str, bytes]) -> tuple[str | None, str | None]:
    """Return ``(header_rels_path, footer_rels_path)`` for the letterhead default header/footer."""
    import xml.etree.ElementTree as ET

    doc_rels_path = "word/_rels/document.xml.rels"
    header_rels_path: str | None = None
    footer_rels_path: str | None = None

    if doc_rels_path in lh_parts:
        rid_to_target = {
            rid: target for rid, _typ, target in _parse_ooxml_relationships(lh_parts[doc_rels_path])
        }
        try:
            root = ET.fromstring(lh_parts["word/document.xml"])
        except (KeyError, ET.ParseError):
            root = None
        if root is not None:
            header_rid: str | None = None
            footer_rid: str | None = None
            for el in root.iter(f"{{{_W_NS}}}headerReference"):
                htype = el.get(f"{{{_W_NS}}}type")
                if htype is None or htype == "default":
                    header_rid = el.get(f"{{{_OD_REL_NS}}}id")
                    break
            for el in root.iter(f"{{{_W_NS}}}footerReference"):
                ftype = el.get(f"{{{_W_NS}}}type")
                if ftype is None or ftype == "default":
                    footer_rid = el.get(f"{{{_OD_REL_NS}}}id")
                    break
            if header_rid and header_rid in rid_to_target:
                rels = _ooxml_rels_part_path(_resolve_word_part_path(rid_to_target[header_rid]))
                if rels in lh_parts:
                    header_rels_path = rels
            if footer_rid and footer_rid in rid_to_target:
                rels = _ooxml_rels_part_path(_resolve_word_part_path(rid_to_target[footer_rid]))
                if rels in lh_parts:
                    footer_rels_path = rels

    if header_rels_path is None and "word/_rels/header1.xml.rels" in lh_parts:
        header_rels_path = "word/_rels/header1.xml.rels"
    if footer_rels_path is None and "word/_rels/footer1.xml.rels" in lh_parts:
        footer_rels_path = "word/_rels/footer1.xml.rels"
    return header_rels_path, footer_rels_path


def _media_paths_from_hf_rels(rels_bytes: bytes | None) -> list[str]:
    if not rels_bytes:
        return []
    paths: list[str] = []
    for _rid, typ, target in _parse_ooxml_relationships(rels_bytes):
        if not target:
            continue
        if typ and "image" in typ.lower():
            paths.append(_resolve_word_part_path(target))
    return paths


def _merge_content_types_for_media(content_types_bytes: bytes, lh_content_types_bytes: bytes) -> bytes:
    """Copy missing ``Default`` entries (e.g. png) from the letterhead package."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(content_types_bytes)
    lh_root = ET.fromstring(lh_content_types_bytes)
    existing_ext = {
        (el.get("Extension") or "").lower()
        for el in root
        if el.tag.rsplit("}", 1)[-1] == "Default"
    }
    for el in lh_root:
        if el.tag.rsplit("}", 1)[-1] != "Default":
            continue
        ext = (el.get("Extension") or "").lower()
        if ext and ext not in existing_ext:
            root.append(el)
            existing_ext.add(ext)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fonts_in_ooxml_bytes(data: bytes) -> set[str]:
    """Return ``w:rFonts`` face names referenced in an OOXML part."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return set()
    return {
        name
        for name in re.findall(r'w:(?:ascii|hAnsi|cs|eastAsia)="([^"]+)"', text)
        if name
    }


def _merge_letterhead_font_table(
    prec_parts: dict[str, bytes],
    lh_parts: dict[str, bytes],
    *,
    ooxml_blobs: Iterable[bytes],
) -> None:
    """Add letterhead ``word/fontTable.xml`` entries for fonts used in copied header/footer parts."""
    import xml.etree.ElementTree as ET
    from copy import deepcopy

    lh_ft = lh_parts.get("word/fontTable.xml")
    prec_ft = prec_parts.get("word/fontTable.xml")
    if not lh_ft or not prec_ft:
        return

    needed: set[str] = set()
    for blob in ooxml_blobs:
        needed |= _fonts_in_ooxml_bytes(blob)
    if not needed:
        return

    lh_root = ET.fromstring(lh_ft)
    prec_root = ET.fromstring(prec_ft)
    have = {
        (el.get(f"{{{_W_NS}}}name") or "").strip()
        for el in prec_root
        if el.tag == f"{{{_W_NS}}}font"
    }
    for el in lh_root:
        if el.tag != f"{{{_W_NS}}}font":
            continue
        name = (el.get(f"{{{_W_NS}}}name") or "").strip()
        if name and name in needed and name not in have:
            prec_root.append(deepcopy(el))
            have.add(name)
    prec_parts["word/fontTable.xml"] = ET.tostring(prec_root, encoding="utf-8", xml_declaration=True)


def _merge_letterhead_layout_settings(prec_parts: dict[str, bytes], lh_parts: dict[str, bytes]) -> None:
    """Apply letterhead Word compatibility settings so header/footer spacing matches the template.

    Precedent scaffolds often ship with a newer ``w:compatSetting`` ``compatibilityMode`` than the
    uploaded letterhead. Footer paragraphs with empty ``w:spacing`` then pick up different default
    line gaps in Word / ONLYOFFICE, making the composed footer visibly taller than the letterhead file.
    """
    import xml.etree.ElementTree as ET
    from copy import deepcopy

    lh_settings = lh_parts.get("word/settings.xml")
    prec_settings_path = "word/settings.xml"
    if not lh_settings or prec_settings_path not in prec_parts:
        return

    lh_root = ET.fromstring(lh_settings)
    prec_root = ET.fromstring(prec_parts[prec_settings_path])
    lh_compat = lh_root.find(f"{{{_W_NS}}}compat")
    if lh_compat is None:
        return
    prec_compat = prec_root.find(f"{{{_W_NS}}}compat")
    if prec_compat is not None:
        prec_root.remove(prec_compat)
    prec_root.append(deepcopy(lh_compat))
    prec_parts[prec_settings_path] = ET.tostring(prec_root, encoding="utf-8", xml_declaration=True)


_RPR_DEFAULT_RE = re.compile(r"<(?:(?:w):)?rPrDefault\b.*?</(?:(?:w):)?rPrDefault>", re.IGNORECASE | re.DOTALL)
_PPR_DEFAULT_RE = re.compile(r"<(?:(?:w):)?pPrDefault\b.*?</(?:(?:w):)?pPrDefault>", re.IGNORECASE | re.DOTALL)


def _merge_letterhead_style_doc_defaults(prec_parts: dict[str, bytes], lh_parts: dict[str, bytes]) -> None:
    """Merge letterhead run defaults (fonts / language) onto the precedent without changing body spacing.

    Headers/footers are normalised separately. Body paragraph spacing must stay as in the letter
    precedent (typically Word's ``after=200`` / ``line=276``) so composed letters match what authors
    see when editing BLANK_LETTER. Overwriting that with single-spacing made generated letters too
    tight; copying the letterhead's paragraph defaults wholesale previously made them too loose when
    the scaffold had extra empty paras.
    """
    lh_styles = lh_parts.get("word/styles.xml")
    prec_path = "word/styles.xml"
    if not lh_styles or prec_path not in prec_parts:
        return
    try:
        lh_text = lh_styles.decode("utf-8")
        prec_text = prec_parts[prec_path].decode("utf-8")
    except UnicodeDecodeError:
        return
    lh_match = _DOC_DEFAULTS_BLOCK_RE.search(lh_text)
    if not lh_match:
        return
    lh_doc_defaults = lh_match.group(0)
    lh_rpr = _RPR_DEFAULT_RE.search(lh_doc_defaults)
    if not lh_rpr:
        return

    prec_match = _DOC_DEFAULTS_BLOCK_RE.search(prec_text)
    prec_ppr = _PPR_DEFAULT_RE.search(prec_match.group(0)) if prec_match else None
    if prec_ppr is None:
        # Precedent has no paragraph defaults — fall back to letterhead (same as pre-fix behaviour).
        prec_ppr = _PPR_DEFAULT_RE.search(lh_doc_defaults)

    combined = "<w:docDefaults>" + lh_rpr.group(0)
    if prec_ppr is not None:
        combined += prec_ppr.group(0)
    combined += "</w:docDefaults>"

    if prec_match:
        prec_text = _DOC_DEFAULTS_BLOCK_RE.sub(combined, prec_text, count=1)
    else:
        prec_text = _STYLES_OPEN_RE.sub(lambda m: m.group(0) + combined, prec_text, count=1)
    prec_parts[prec_path] = prec_text.encode("utf-8")


def _normalize_hf_paragraph_spacing(hf_xml: bytes, *, part_path: str = "") -> bytes:
    """Pin single-line spacing on header/footer paragraphs that leave ``w:spacing`` empty."""
    try:
        text = hf_xml.decode("utf-8")
    except UnicodeDecodeError:
        return hf_xml

    def _repl_empty_spacing(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        if re.search(r"(?:(?:w):)?(?:after|before|line|lineRule)=", attrs, re.IGNORECASE):
            return match.group(0)
        return '<w:spacing w:after="0" w:before="0" w:line="240" w:lineRule="auto"/>'

    patched = re.sub(
        r"<(?:(?:w):)?spacing\b([^/>]*)/>",
        _repl_empty_spacing,
        text,
        flags=re.IGNORECASE,
    )
    if "footer" not in part_path.lower() or re.search(r"<(?:(?:w):)?spacing\b", patched, re.IGNORECASE):
        if patched == text:
            return hf_xml
        return patched.encode("utf-8")

    # Footers with no ``w:spacing`` at all (e.g. python-docx default Footer style): add explicitly.
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(patched.encode("utf-8"))
    except ET.ParseError:
        return patched.encode("utf-8") if patched != text else hf_xml

    p_tag = f"{{{_W_NS}}}p"
    ppr_tag = f"{{{_W_NS}}}pPr"
    sp_tag = f"{{{_W_NS}}}spacing"
    changed = False
    for p_el in root.findall(f".//{p_tag}"):
        p_pr = p_el.find(ppr_tag)
        if p_pr is None:
            continue
        if p_pr.find(sp_tag) is not None:
            continue
        spacing = ET.SubElement(p_pr, sp_tag)
        spacing.set(f"{{{_W_NS}}}after", "0")
        spacing.set(f"{{{_W_NS}}}before", "0")
        spacing.set(f"{{{_W_NS}}}line", "240")
        spacing.set(f"{{{_W_NS}}}lineRule", "auto")
        changed = True
    if not changed:
        return hf_xml
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _paragraph_visible_text(p_el: Any) -> str:
    """Visible text in a paragraph (``w:t`` only), ignoring drawings."""
    from docx.oxml.ns import qn

    parts: list[str] = []
    for node in p_el.iter(qn("w:t")):
        if node.text:
            parts.append(node.text)
    return "".join(parts)


def _doc_defaults_spacing_after(doc: Any) -> str:
    """``w:spacing/@w:after`` from ``docDefaults``, else Word-normal ``200``."""
    from docx.oxml.ns import qn

    try:
        styles = doc.styles.element
    except Exception:
        return "200"
    after = None
    for node in styles.iter(qn("w:docDefaults")):
        for sp in node.iter(qn("w:spacing")):
            after = sp.get(qn("w:after")) or after
    return after or "200"


def pin_empty_body_paragraph_spacing(doc_bytes: bytes) -> bytes:
    """Normalise bare ``<w:spacing/>`` so composed letters match editing the body precedent.

    Empty spacer paragraphs must not pick up ``docDefaults`` ``after`` (that becomes
    “blank line + paragraph spacing”). Content paragraphs with bare spacing get an explicit
    ``after`` from ``docDefaults`` so OnlyOffice keeps the Dear→body gap (bare ``<w:spacing/>``
    alone is treated as after=0 by some renderers after letterhead merge).
    """
    import io

    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(doc_bytes))
    default_after = _doc_defaults_spacing_after(doc)
    p_tag = qn("w:p")
    ppr_tag = qn("w:pPr")
    sp_tag = qn("w:spacing")
    changed = False
    for p_el in doc.element.body.iter(p_tag):
        xml = p_el.xml if hasattr(p_el, "xml") else ""
        if "a:blip" in xml or "v:imagedata" in xml or "imagedata" in xml.lower():
            continue
        p_pr = p_el.find(ppr_tag)
        if p_pr is None:
            continue
        spacing = p_pr.find(sp_tag)
        if spacing is None:
            continue
        # Only rewrite spacers that never set before/after (empty ``<w:spacing/>`` or line-only).
        if spacing.get(qn("w:after")) is not None or spacing.get(qn("w:before")) is not None:
            continue
        is_content = bool(_paragraph_visible_text(p_el).strip())
        spacing.set(qn("w:before"), "0")
        spacing.set(qn("w:after"), default_after if is_content else "0")
        if spacing.get(qn("w:line")) is None:
            spacing.set(qn("w:line"), "276")
            spacing.set(qn("w:lineRule"), "auto")
        changed = True
    if not changed:
        return doc_bytes
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def reapply_letterhead_layout_package_bytes(doc_bytes: bytes, letterhead_bytes: bytes) -> bytes:
    """Re-apply letterhead layout metadata after other .docx normalisation (e.g. en-GB proofing)."""
    lh_parts = _read_docx_zip_parts(letterhead_bytes)
    prec_parts = _read_docx_zip_parts(doc_bytes)
    _merge_letterhead_layout_settings(prec_parts, lh_parts)
    _merge_letterhead_style_doc_defaults(prec_parts, lh_parts)
    for path in list(prec_parts):
        if _HF_PART_RE.match(path):
            prec_parts[path] = _normalize_hf_paragraph_spacing(prec_parts[path], part_path=path)
    return _write_docx_zip_parts(prec_parts)


def _copy_letterhead_media_for_rels(
    rels_bytes: bytes | None,
    *,
    lh_parts: dict[str, bytes],
    prec_parts: dict[str, bytes],
) -> bytes | None:
    if not rels_bytes:
        return rels_bytes
    updated = rels_bytes
    for media_path in _media_paths_from_hf_rels(rels_bytes):
        if media_path not in lh_parts:
            continue
        dest_path = media_path
        if dest_path in prec_parts and prec_parts[dest_path] != lh_parts[media_path]:
            base = dest_path.rsplit("/", 1)[-1]
            dest_path = f"word/media/lh_{base}"
            n = 0
            while dest_path in prec_parts:
                n += 1
                dest_path = f"word/media/lh_{n}_{base}"
            old_target = media_path.removeprefix("word/")
            new_target = dest_path.removeprefix("word/")
            updated = updated.replace(
                f'Target="{old_target}"'.encode(),
                f'Target="{new_target}"'.encode(),
            )
        prec_parts[dest_path] = lh_parts[media_path]
    return updated


def _append_ooxml_relationship(rels_bytes: bytes, rid: str, typ: str, target: str) -> bytes:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(rels_bytes)
    ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    el = ET.Element(f"{{{ns}}}Relationship")
    el.set("Id", rid)
    el.set("Type", typ)
    el.set("Target", target)
    root.append(el)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _next_ooxml_rel_id(existing: set[str]) -> str:
    n = 1
    while True:
        rid = f"rId{n}"
        if rid not in existing:
            return rid
        n += 1


def _merge_letterhead_document_body_media_rels(
    prec_parts: dict[str, bytes],
    lh_parts: dict[str, bytes],
) -> None:
    """Copy document-body image rels/media referenced in the composed story but missing from the package."""
    doc_xml_path = "word/document.xml"
    doc_rels_path = "word/_rels/document.xml.rels"
    prec_xml = prec_parts.get(doc_xml_path)
    lh_rels = lh_parts.get(doc_rels_path)
    prec_rels = prec_parts.get(doc_rels_path)
    if not prec_xml or not lh_rels or not prec_rels:
        return

    try:
        prec_xml_text = prec_xml.decode("utf-8")
    except UnicodeDecodeError:
        return

    lh_rid_to_rel = {
        rid: (typ, target) for rid, typ, target in _parse_ooxml_relationships(lh_rels) if rid
    }
    prec_rid_to_rel = {
        rid: (typ, target) for rid, typ, target in _parse_ooxml_relationships(prec_rels) if rid
    }
    used_rids = set(prec_rid_to_rel)

    def _add_image_rel(old_rid: str) -> None:
        nonlocal prec_xml_text, prec_rels, used_rids
        lh_rel = lh_rid_to_rel.get(old_rid)
        if not lh_rel:
            return
        typ, target = lh_rel
        if not typ or "image" not in typ.lower():
            return
        media_path = _resolve_word_part_path(target)
        if media_path not in lh_parts:
            return
        new_rid = _next_ooxml_rel_id(used_rids)
        used_rids.add(new_rid)
        dest_path = media_path
        rel_target = target.lstrip("/")
        if dest_path in prec_parts and prec_parts[dest_path] != lh_parts[media_path]:
            base = dest_path.rsplit("/", 1)[-1]
            dest_path = f"word/media/lh_{base}"
            n = 0
            while dest_path in prec_parts:
                n += 1
                dest_path = f"word/media/lh_{n}_{base}"
            rel_target = dest_path.removeprefix("word/")
        prec_parts[dest_path] = lh_parts[media_path]
        prec_rels = _append_ooxml_relationship(prec_rels, new_rid, typ, rel_target)
        prec_rid_to_rel[new_rid] = (typ, rel_target)
        return new_rid

    for rid in set(re.findall(r'r:embed="([^"]+)"', prec_xml_text)):
        prec_rel = prec_rid_to_rel.get(rid)
        if prec_rel and "image" in prec_rel[0].lower():
            continue
        new_rid = _add_image_rel(rid)
        if new_rid:
            prec_xml_text = prec_xml_text.replace(f'r:embed="{rid}"', f'r:embed="{new_rid}"')

    for rid, (typ, _target) in lh_rid_to_rel.items():
        if "image" not in typ.lower():
            continue
        if f'r:id="{rid}"' not in prec_xml_text:
            continue
        prec_rel = prec_rid_to_rel.get(rid)
        if prec_rel and "image" in prec_rel[0].lower():
            continue
        new_rid = _add_image_rel(rid)
        if new_rid:
            prec_xml_text = re.sub(
                rf'(<v:imagedata[^>]*r:id="){re.escape(rid)}(")',
                rf"\g<1>{new_rid}\2",
                prec_xml_text,
            )

    prec_parts[doc_xml_path] = prec_xml_text.encode("utf-8")
    prec_parts[doc_rels_path] = prec_rels


def _merge_letterhead_package_assets(precedent_bytes: bytes, letterhead_bytes: bytes) -> bytes:
    """Copy letterhead ``word/media`` parts and header/footer parts into a composed document."""
    lh_parts = _read_docx_zip_parts(letterhead_bytes)
    prec_parts = _read_docx_zip_parts(precedent_bytes)

    lh_refs = _hf_parts_by_reference(lh_parts)
    prec_refs = _hf_parts_by_reference(prec_parts)

    copied_hf_xml: list[bytes] = []
    for role, lh_path in lh_refs.items():
        prec_path = prec_refs.get(role)
        if not prec_path or lh_path not in lh_parts:
            continue
        prec_parts[prec_path] = _normalize_hf_paragraph_spacing(lh_parts[lh_path], part_path=prec_path)
        copied_hf_xml.append(lh_parts[lh_path])
        lh_rels_path = _ooxml_rels_part_path(lh_path)
        prec_rels_path = _ooxml_rels_part_path(prec_path)
        if lh_rels_path not in lh_parts:
            continue
        merged_rels = _copy_letterhead_media_for_rels(
            lh_parts[lh_rels_path],
            lh_parts=lh_parts,
            prec_parts=prec_parts,
        )
        if merged_rels is not None:
            prec_parts[prec_rels_path] = merged_rels

    _merge_letterhead_document_body_media_rels(prec_parts, lh_parts)

    for path, data in lh_parts.items():
        if path.startswith("word/media/") and path not in prec_parts:
            prec_parts[path] = data

    if "[Content_Types].xml" in prec_parts and "[Content_Types].xml" in lh_parts:
        prec_parts["[Content_Types].xml"] = _merge_content_types_for_media(
            prec_parts["[Content_Types].xml"],
            lh_parts["[Content_Types].xml"],
        )

    _merge_letterhead_layout_settings(prec_parts, lh_parts)
    _merge_letterhead_style_doc_defaults(prec_parts, lh_parts)
    _merge_letterhead_font_table(prec_parts, lh_parts, ooxml_blobs=copied_hf_xml)

    return _write_docx_zip_parts(prec_parts)


def apply_digital_letterhead_headers_footers(precedent_bytes: bytes, letterhead_bytes: bytes) -> bytes:
    """Copy header and footer XML from the letterhead .docx onto every section of the precedent .docx.

    Intended for “typical” letterhead: logos and firm lines live in headers/footers; precedent body
    stays in the document story so page 1 shows letterhead + letter content together. Some firm
    templates (e.g. Ashbourne and Finch) also place the logo in the **document body** as a floating masthead;
    those elements are prepended before the precedent story. Embedded images are copied from
    ``word/media`` and relationship parts are merged into the composed package.

    Also copies **section page geometry** (margins, header/footer offsets, page size) from the
    letterhead's first section onto every precedent section so padding matches the uploaded template.
    """
    import io
    from copy import deepcopy

    from docx import Document

    lh = Document(io.BytesIO(letterhead_bytes))
    prec = Document(io.BytesIO(precedent_bytes))

    def _copy_hf_elements(src_hf: Any, tgt_hf: Any) -> None:
        src_el = src_hf._element
        tgt_el = tgt_hf._element
        for child in list(tgt_el):
            tgt_el.remove(child)
        for child in src_el:
            tgt_el.append(deepcopy(child))

    _HF_ATTRS = (
        "header",
        "footer",
        "first_page_header",
        "first_page_footer",
        "even_page_header",
        "even_page_footer",
    )

    src_sec = lh.sections[0]
    for tgt_sec in prec.sections:
        _copy_section_page_geometry(src_sec, tgt_sec)
        tgt_sec.different_first_page_header_footer = src_sec.different_first_page_header_footer
        for attr in _HF_ATTRS:
            _copy_hf_elements(getattr(src_sec, attr), getattr(tgt_sec, attr))

    masthead = [
        deepcopy(el) for el in extract_letterhead_body_masthead_elements_for_document(lh)
    ]
    if masthead:
        prec_body = prec.element.body
        for offset, el in enumerate(masthead):
            prec_body.insert(offset, el)

    out = io.BytesIO()
    prec.save(out)
    return _merge_letterhead_package_assets(out.getvalue(), letterhead_bytes)

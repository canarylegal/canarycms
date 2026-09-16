"""OOXML merge token / MERGEFIELD replacement and related helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .merge_fields import (
    IMAGE_PRECEDENT_CODES,
    _ADDITIONAL_CLIENT_NAME_CODES,
    _core_name_company_for_contact,
)

def _zip_archive_basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _find_ooxml_content_types_member(names: list[str]) -> str | None:
    """Return the Zip member name for ``[Content_Types].xml`` (case-insensitive basename)."""

    for n in names:
        if _zip_archive_basename(n).lower() == "[content_types].xml":
            return n
    return None


def _find_ooxml_document_xml_member(names: list[str]) -> str | None:
    """Return the Zip member for ``word/document.xml`` (case-insensitive ``word`` / ``document.xml``)."""

    for n in names:
        norm = n.replace("\\", "/")
        parts = norm.split("/")
        if len(parts) >= 2 and parts[-2].lower() == "word" and parts[-1].lower() == "document.xml":
            return n
    return None


def validate_docx_package_bytes(raw: bytes) -> None:
    """Raise ``ValueError`` with a plain-language message if ``raw`` is not a WordprocessingML (.docx) package."""

    import io
    import zipfile

    if not raw:
        raise ValueError("The file is empty.")
    if not raw.startswith(b"PK"):
        raise ValueError(
            "This file does not look like a .docx — real Office documents are ZIP archives whose bytes start with PK. "
            "Common causes: the browser saved an HTML/login/error page with a .docx name, the download failed, "
            "or the file is not Word format. Open it in Word and use Save As → Word Document (.docx), or use the "
            "Canary-generated Universal-letter-precedent.docx from the backend container."
        )
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise ValueError(
            "This is not a valid ZIP archive — the .docx may be truncated, corrupted, or incomplete."
        ) from e
    try:
        names = zf.namelist()
        ct_name = _find_ooxml_content_types_member(names)
        if ct_name is None:
            raise ValueError(
                "Missing [Content_Types].xml — this is not a valid Office Open XML (.docx) package. "
                "Re-save from Microsoft Word (or export as .docx from Google Docs). "
                "If you renamed another format to .docx, merge will not work."
            )
        doc_name = _find_ooxml_document_xml_member(names)
        if doc_name is None:
            raise ValueError("Missing word/document.xml — not a valid Word .docx.")
        try:
            ct_raw = zf.read(ct_name)
        except KeyError as e:
            raise ValueError(
                "The archive lists [Content_Types].xml but it could not be read — the file may be corrupted."
            ) from e
        if not ct_raw.strip():
            raise ValueError(
                "[Content_Types].xml is empty — this .docx package is invalid. Re-save the document from Word."
            )
        if not ct_raw.lstrip().startswith(b"<"):
            raise ValueError(
                "[Content_Types].xml is not valid XML — this .docx package is broken. Re-save from Word."
            )
    finally:
        zf.close()


def is_invalid_ooxml_merge_exception(exc: BaseException) -> bool:
    """True when ``exc`` usually means bytes are not a loadable Word .docx (client/template issue, HTTP 400)."""

    import zipfile

    if isinstance(exc, (zipfile.BadZipFile, KeyError, OSError)):
        return True
    try:
        from docx.opc.exceptions import PackageNotFoundError

        if isinstance(exc, PackageNotFoundError):
            return True
    except ImportError:
        pass
    lowered = str(exc).lower()
    if "there is no item named" in lowered and "content_types" in lowered:
        return True
    if "bad zipfile" in lowered or "bad magic number for file header" in lowered:
        return True
    # python-docx / lxml load of corrupt OOXML
    if type(exc).__name__ == "XMLSyntaxError":
        return True
    return False

def _replace_in_text(text: str, fields: dict[str, str]) -> str:
    # Longest keys first so a shorter placeholder can never break a longer token (defensive).
    for code in sorted(fields.keys(), key=len, reverse=True):
        text = text.replace(code, fields[code])
    return text


def _normalize_post_merge_whitespace(text: str) -> str:
    """Trim gaps left when earlier client slots merge empty within the same paragraph.

    Templates often interleave ``[TITLE] [FIRST_NAME] … [TITLE_2] …`` with literal spaces.
    When slot 1 is empty, spaces remain before slot 2; strip leading horizontal whitespace
    per line and collapse doubled spaces/tabs inside non-empty lines.
    """
    lines: list[str] = []
    for ln in text.split("\n"):
        if not ln.strip():
            lines.append("")
            continue
        collapsed = re.sub(r"[ \t]{2,}", " ", ln)
        lines.append(collapsed.lstrip())
    return "\n".join(lines)


# Inner token without brackets, e.g. TITLE, LAST_NAME_3 — for slot detection.
_NAME_CODE_INNERS: frozenset[str] = frozenset(c[1:-1] for c in _ADDITIONAL_CLIENT_NAME_CODES)

# ``[CODE]`` or ``[modifiers:CODE]`` where modifiers are one or more of b, i, u.
_MERGE_TOKEN_RE = re.compile(
    r"\[\s*((?:[biu]+)\s*:\s*)?([A-Z0-9_]+)\s*\]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _MergeTextSegment:
    text: str
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None


def _parse_modifier_letters(mod: str | None) -> tuple[bool | None, bool | None, bool | None]:
    if not mod:
        return None, None, None
    letters = {c for c in mod.lower() if c in "biu"}
    return (
        True if "b" in letters else None,
        True if "i" in letters else None,
        True if "u" in letters else None,
    )


def _paragraph_has_modifier_tokens(text: str) -> bool:
    return bool(re.search(r"\[\s*(?:[biu]+)\s*:", text, re.IGNORECASE))


def _merge_token_pattern_for_fields(fields: Mapping[str, str]) -> re.Pattern[str]:
    inners = sorted({k[1:-1] for k in fields}, key=len, reverse=True)
    if not inners:
        return re.compile(r"(?!x)")
    inner_alt = "|".join(re.escape(c) for c in inners)
    return re.compile(rf"\[\s*(?:[biu]+\s*:\s*)?(?:{inner_alt})\s*\]", re.IGNORECASE)


def _paragraph_has_merge_tokens(text: str, fields: Mapping[str, str]) -> bool:
    return _merge_token_pattern_for_fields(fields).search(text) is not None


def _replace_merge_tokens_to_segments(text: str, fields: Mapping[str, str]) -> list[_MergeTextSegment]:
    segments: list[_MergeTextSegment] = []
    pos = 0
    for m in _MERGE_TOKEN_RE.finditer(text):
        if m.start() > pos:
            segments.append(_MergeTextSegment(text[pos : m.start()]))
        inner = m.group(2).upper()
        key = f"[{inner}]"
        if key in fields:
            bold, italic, underline = _parse_modifier_letters(m.group(1))
            value = fields[key]
            if value:
                segments.append(_MergeTextSegment(value, bold, italic, underline))
        else:
            segments.append(_MergeTextSegment(m.group(0)))
        pos = m.end()
    if pos < len(text):
        segments.append(_MergeTextSegment(text[pos:]))
    return segments


def _segments_plain_text(segments: list[_MergeTextSegment]) -> str:
    return "".join(s.text for s in segments)


def _trim_leading_segment_whitespace(segments: list[_MergeTextSegment]) -> list[_MergeTextSegment]:
    out: list[_MergeTextSegment] = []
    trimmed = False
    for seg in segments:
        if trimmed or not seg.text.strip():
            out.append(seg)
            continue
        text = seg.text.lstrip()
        out.append(_MergeTextSegment(text, seg.bold, seg.italic, seg.underline))
        trimmed = True
    return out


def _run_element_formatting(r_el: Any) -> tuple[bool | None, bool | None, bool | None]:
    """Read direct bold / italic / underline from a ``w:r`` element."""
    from docx.oxml.ns import qn

    rpr = r_el.find(qn("w:rPr"))
    if rpr is None:
        return None, None, None

    def _tri_state(tag: str) -> bool | None:
        el = rpr.find(qn(tag))
        if el is None:
            return None
        val = el.get(qn("w:val"))
        if val is None or val in ("1", "true", "on"):
            return True
        if val in ("0", "false", "off"):
            return False
        return True

    return _tri_state("w:b"), _tri_state("w:i"), _tri_state("w:u")


def _paragraph_to_formatted_segments(para: Any) -> list[_MergeTextSegment]:
    """Extract paragraph text as formatted segments (includes runs inside ``w:hyperlink``)."""
    from docx.oxml.ns import qn

    segments: list[_MergeTextSegment] = []
    for r in para._p.iter(qn("w:r")):
        parts: list[str] = []
        for child in r:
            tag = child.tag
            if tag == qn("w:t"):
                if child.text:
                    parts.append(child.text)
            elif tag == qn("w:tab"):
                parts.append("\t")
            elif tag in (qn("w:br"), qn("w:cr")):
                parts.append("\n")
            elif tag == qn("w:noBreakHyphen"):
                parts.append("\u2011")
            elif tag == qn("w:softHyphen"):
                parts.append("\u00ad")
        text = "".join(parts)
        if not text:
            continue
        bold, italic, underline = _run_element_formatting(r)
        segments.append(_MergeTextSegment(text, bold, italic, underline))
    return _coalesce_formatted_segments(segments)


def _coalesce_formatted_segments(segments: list[_MergeTextSegment]) -> list[_MergeTextSegment]:
    if not segments:
        return []
    out: list[_MergeTextSegment] = []
    cur = segments[0]
    for seg in segments[1:]:
        if seg.bold == cur.bold and seg.italic == cur.italic and seg.underline == cur.underline:
            cur = _MergeTextSegment(cur.text + seg.text, cur.bold, cur.italic, cur.underline)
        else:
            out.append(cur)
            cur = seg
    out.append(cur)
    return out


def _slice_formatted_segments(
    segments: list[_MergeTextSegment],
    start: int,
    end: int,
) -> list[_MergeTextSegment]:
    if start >= end:
        return []
    result: list[_MergeTextSegment] = []
    pos = 0
    for seg in segments:
        seg_start = pos
        seg_end = pos + len(seg.text)
        pos = seg_end
        if seg_end <= start or seg_start >= end:
            continue
        slice_start = max(start, seg_start) - seg_start
        slice_end = min(end, seg_end) - seg_start
        result.append(
            _MergeTextSegment(seg.text[slice_start:slice_end], seg.bold, seg.italic, seg.underline)
        )
    return _coalesce_formatted_segments(result)


def _formatting_for_segment_range(
    segments: list[_MergeTextSegment],
    start: int,
    end: int,
) -> tuple[bool | None, bool | None, bool | None]:
    sliced = _slice_formatted_segments(segments, start, end)
    if not sliced:
        return None, None, None
    b0, i0, u0 = sliced[0].bold, sliced[0].italic, sliced[0].underline
    for seg in sliced[1:]:
        if seg.bold != b0 or seg.italic != i0 or seg.underline != u0:
            return None, None, None
    return b0, i0, u0


def _replace_merge_tokens_in_formatted_segments(
    segments: list[_MergeTextSegment],
    fields: Mapping[str, str],
) -> list[_MergeTextSegment]:
    """Replace merge tokens while preserving formatting on surrounding static text."""
    text = _segments_plain_text(segments)
    if not _paragraph_has_merge_tokens(text, fields):
        return segments
    result: list[_MergeTextSegment] = []
    pos = 0
    for m in _MERGE_TOKEN_RE.finditer(text):
        if m.start() > pos:
            result.extend(_slice_formatted_segments(segments, pos, m.start()))
        inner = m.group(2).upper()
        key = f"[{inner}]"
        if key in fields:
            bold, italic, underline = _parse_modifier_letters(m.group(1))
            if bold is None and italic is None and underline is None:
                bold, italic, underline = _formatting_for_segment_range(segments, m.start(), m.end())
            value = fields[key]
            if value:
                result.append(_MergeTextSegment(value, bold, italic, underline))
        else:
            result.extend(_slice_formatted_segments(segments, m.start(), m.end()))
        pos = m.end()
    if pos < len(text):
        result.extend(_slice_formatted_segments(segments, pos, len(text)))
    return _coalesce_formatted_segments(result)


def _insert_and_between_adjacent_name_placeholders_in_segments(
    segments: list[_MergeTextSegment],
    sep_flags: dict[tuple[int, int], bool],
) -> list[_MergeTextSegment]:
    """Like :func:`_insert_and_between_adjacent_name_placeholders` but keeps static formatting."""
    text = _segments_plain_text(segments)
    if not sep_flags:
        return segments
    matches = list(_MERGE_TOKEN_RE.finditer(text))
    if len(matches) < 2:
        return segments
    result: list[_MergeTextSegment] = []
    pos = 0
    i = 0
    while i < len(matches):
        m = matches[i]
        result.extend(_slice_formatted_segments(segments, pos, m.start()))
        result.extend(_slice_formatted_segments(segments, m.start(), m.end()))
        pos = m.end()
        if i + 1 < len(matches):
            m2 = matches[i + 1]
            s1 = _name_slot_from_placeholder_inner(m.group(2))
            s2 = _name_slot_from_placeholder_inner(m2.group(2))
            if (
                s1 is not None
                and s2 is not None
                and s2 == s1 + 1
                and sep_flags.get((s1, s2), False)
            ):
                result.append(_MergeTextSegment(" and "))
                pos = m2.start()
        i += 1
    result.extend(_slice_formatted_segments(segments, pos, len(text)))
    return _coalesce_formatted_segments(result)


def _segments_have_direct_formatting(segments: list[_MergeTextSegment]) -> bool:
    return any(
        s.bold is not None or s.italic is not None or s.underline is not None for s in segments
    )


def _name_slot_from_placeholder_inner(inner: str) -> int | None:
    """Return 1–4 for per-client name/company placeholders; ``None`` for other codes."""
    if inner in _NAME_CODE_INNERS:
        return 1
    m = re.fullmatch(r"(.+)_([234])$", inner)
    if not m:
        return None
    base, suf = m.group(1), m.group(2)
    if base not in _NAME_CODE_INNERS:
        return None
    return int(suf)


def _contact_has_any_name_or_company_field(contact: Any | None) -> bool:
    core = _core_name_company_for_contact(contact)
    return any((v or "").strip() for v in core.values())


def _inter_client_sep_flags(ordered_clients: list[Any] | None) -> dict[tuple[int, int], bool]:
    """When True, insert `` and `` between adjacent name placeholders for slots (a, b)."""
    if not ordered_clients:
        return {}
    out: dict[tuple[int, int], bool] = {}
    n = min(len(ordered_clients), 4)
    for i in range(n - 1):
        a, b = ordered_clients[i], ordered_clients[i + 1]
        if _contact_has_any_name_or_company_field(a) and _contact_has_any_name_or_company_field(b):
            out[(i + 1, i + 2)] = True
    return out


def _insert_and_between_adjacent_name_placeholders(
    text: str,
    sep_flags: dict[tuple[int, int], bool],
) -> str:
    """Insert the word ``and`` between consecutive client name placeholders when ``sep_flags`` says to.

    Matches only **adjacent** ``[CODE]`` tokens in this string (same paragraph). Whitespace
    between them is replaced by `` and `` (spaces around *and*).
    """
    if not sep_flags:
        return text
    matches = list(_MERGE_TOKEN_RE.finditer(text))
    if len(matches) < 2:
        return text
    parts: list[str] = []
    pos = 0
    i = 0
    while i < len(matches):
        m = matches[i]
        parts.append(text[pos : m.start()])
        parts.append(m.group(0))
        pos = m.end()
        if i + 1 < len(matches):
            m2 = matches[i + 1]
            s1 = _name_slot_from_placeholder_inner(m.group(2))
            s2 = _name_slot_from_placeholder_inner(m2.group(2))
            if (
                s1 is not None
                and s2 is not None
                and s2 == s1 + 1
                and sep_flags.get((s1, s2), False)
            ):
                parts.append(" and ")
                pos = m2.start()
        i += 1
    parts.append(text[pos:])
    return "".join(parts)


def _xml_escape_ooxml_text(value: str) -> str:
    """Escape text merged into ``<w:t>`` (and similar) XML character data."""
    from xml.sax.saxutils import escape

    return escape(value, {'"': "&quot;", "'": "&apos;"})


def _ooxml_part_paths_for_merge() -> tuple[str, ...]:
    """Part paths inside the .docx zip that may contain visible merge tokens."""
    return (
        "word/document.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
    )


def _ooxml_part_path_matches(name: str) -> bool:
    if name in _ooxml_part_paths_for_merge():
        return True
    if name.startswith("word/header") and name.endswith(".xml"):
        return True
    if name.startswith("word/footer") and name.endswith(".xml"):
        return True
    return False


_MERGE_FIELD_NAME_RE = re.compile(r"MERGEFIELD\s+([A-Za-z0-9_]+)")


def _mergefield_name_from_instr(instr: str) -> str | None:
    m = _MERGE_FIELD_NAME_RE.search(instr or "")
    return m.group(1) if m else None


def _make_plain_text_run_element(parent_el: Any, text: str) -> Any:
    from docx.oxml.ns import qn

    r_tag = qn("w:r")
    t_tag = qn("w:t")
    r = parent_el.makeelement(r_tag, {})
    attrs = {qn("xml:space"): "preserve"} if text.strip() != text else {}
    t = parent_el.makeelement(t_tag, attrs)
    t.text = text
    r.append(t)
    return r


def _canary_code_for_mergefield(name: str, field_map: Mapping[str, str]) -> str:
    return field_map.get(name, f"[{name.upper()}]")


def _replace_mergefields_in_paragraph_element(p_el: Any, field_map: Mapping[str, str]) -> bool:
    from docx.oxml.ns import qn

    changed = False
    fld_simple_tag = qn("w:fldSimple")
    instr_attr = qn("w:instr")
    for fld in list(p_el.findall(fld_simple_tag)):
        name = _mergefield_name_from_instr(fld.get(instr_attr) or "")
        if not name:
            continue
        code = _canary_code_for_mergefield(name, field_map)
        new_r = _make_plain_text_run_element(p_el, code)
        idx = list(p_el).index(fld)
        p_el.remove(fld)
        p_el.insert(idx, new_r)
        changed = True

    r_tag = qn("w:r")
    fld_char_tag = qn("w:fldChar")
    instr_tag = qn("w:instrText")
    t_tag = qn("w:t")
    fld_type_attr = qn("w:fldCharType")

    while True:
        children = list(p_el)
        replaced = False
        for i, child in enumerate(children):
            if child.tag != r_tag:
                continue
            fc = child.find(fld_char_tag)
            if fc is None or fc.get(fld_type_attr) != "begin":
                continue
            field_name: str | None = None
            instr_texts: list[str] = []
            end_j: int | None = None
            separate_j: int | None = None
            for j in range(i + 1, len(children)):
                cj = children[j]
                if cj.tag != r_tag:
                    continue
                instr = cj.find(instr_tag)
                if instr is not None and (instr.text or "").strip():
                    txt = (instr.text or "").strip()
                    instr_texts.append(txt)
                    field_name = _mergefield_name_from_instr(txt) or field_name
                fcj = cj.find(fld_char_tag)
                if fcj is not None:
                    if fcj.get(fld_type_attr) == "separate":
                        separate_j = j
                    if fcj.get(fld_type_attr) == "end":
                        end_j = j
                        break
            if field_name is None or end_j is None:
                continue
            if any(t.upper().startswith("IF") for t in instr_texts):
                continue
            code = _canary_code_for_mergefield(field_name, field_map)
            new_r = _make_plain_text_run_element(p_el, code)
            for k in range(end_j, i - 1, -1):
                p_el.remove(children[k])
            p_el.insert(i, new_r)
            changed = True
            replaced = True
            break
        if not replaced:
            break
    return changed


def _cleanup_word_if_fields_in_paragraph_element(p_el: Any) -> bool:
    """Remove Word IF field markup, mapping conditional job-title fields to ``[FEE_EARNER_JOB_TITLE]``."""
    from docx.oxml.ns import qn

    changed = False
    r_tag = qn("w:r")
    fld_char_tag = qn("w:fldChar")
    instr_tag = qn("w:instrText")
    t_tag = qn("w:t")
    fld_type_attr = qn("w:fldCharType")

    while True:
        children = list(p_el)
        replaced = False
        for i, child in enumerate(children):
            if child.tag != r_tag:
                continue
            fc = child.find(fld_char_tag)
            if fc is None or fc.get(fld_type_attr) != "begin":
                continue
            instr_texts: list[str] = []
            end_j: int | None = None
            for j in range(i + 1, len(children)):
                cj = children[j]
                if cj.tag != r_tag:
                    continue
                instr = cj.find(instr_tag)
                if instr is not None and (instr.text or "").strip():
                    instr_texts.append((instr.text or "").strip())
                fcj = cj.find(fld_char_tag)
                if fcj is not None and fcj.get(fld_type_attr) == "end":
                    end_j = j
                    break
            if end_j is None:
                continue
            if not any(t.upper().startswith("IF") for t in instr_texts):
                continue
            replacement = "[FEE_EARNER_JOB_TITLE]"
            new_r = _make_plain_text_run_element(p_el, replacement)
            for k in range(end_j, i - 1, -1):
                p_el.remove(children[k])
            p_el.insert(i, new_r)
            changed = True
            replaced = True
            break
        if not replaced:
            break
    return changed


def _cleanup_word_field_markup_in_paragraph_element(p_el: Any) -> bool:
    """Remove leftover Word field markup after MERGEFIELD conversion."""
    from docx.oxml.ns import qn

    changed = False
    r_tag = qn("w:r")
    fld_char_tag = qn("w:fldChar")
    instr_tag = qn("w:instrText")
    t_tag = qn("w:t")
    fld_type_attr = qn("w:fldCharType")

    while True:
        children = list(p_el)
        replaced = False
        for i, child in enumerate(children):
            if child.tag != r_tag:
                continue
            fc = child.find(fld_char_tag)
            if fc is None or fc.get(fld_type_attr) != "begin":
                continue
            instr_texts: list[str] = []
            end_j: int | None = None
            separate_j: int | None = None
            display_text = ""
            for j in range(i + 1, len(children)):
                cj = children[j]
                if cj.tag != r_tag:
                    continue
                instr = cj.find(instr_tag)
                if instr is not None and (instr.text or "").strip():
                    instr_texts.append((instr.text or "").strip())
                fcj = cj.find(fld_char_tag)
                if fcj is not None:
                    if fcj.get(fld_type_attr) == "separate":
                        separate_j = j
                    if fcj.get(fld_type_attr) == "end":
                        end_j = j
                        break
                if separate_j is not None and cj.find(t_tag) is not None:
                    display_text = "".join((t.text or "") for t in cj.iter(t_tag))
            if end_j is None:
                continue
            replacement = display_text.strip()
            if not replacement:
                for txt in instr_texts:
                    quoted = re.findall(r'"([^"]+)"', txt)
                    for q in reversed(quoted):
                        if q.strip():
                            replacement = q.strip()
                            break
                    if replacement:
                        break
            if not replacement:
                for k in range(end_j, i - 1, -1):
                    p_el.remove(children[k])
                changed = True
                replaced = True
                break
            new_r = _make_plain_text_run_element(p_el, replacement)
            for k in range(end_j, i - 1, -1):
                p_el.remove(children[k])
            p_el.insert(i, new_r)
            changed = True
            replaced = True
            break
        if not replaced:
            break
    return changed


def _normalize_merge_code_paragraph_element(p_el: Any) -> bool:
    """Collapse repeated ``[CODE]`` tokens and rewrite the paragraph as plain runs."""
    from docx.oxml.ns import qn

    t_tag = qn("w:t")
    text = "".join((t.text or "") for t in p_el.iter(t_tag))
    if "[" not in text:
        return False
    normalized = re.sub(r"(\[[A-Z0-9_]+\])(?:\1)+", r"\1", text)
    normalized = re.sub(r"(\[[A-Z0-9_]+\])(?:\s+\1)+", r"\1", normalized)
    if normalized == text:
        return False
    r_tag = qn("w:r")
    for child in list(p_el):
        if child.tag == r_tag:
            p_el.remove(child)
    p_el.append(_make_plain_text_run_element(p_el, normalized))
    return True


def replace_word_mergefields_in_docx_bytes(
    src_bytes: bytes,
    field_map: Mapping[str, str],
) -> bytes:
    """Replace Word ``MERGEFIELD`` structures with Canary ``[CODE]`` placeholder text."""
    import io

    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(src_bytes))
    p_tag = qn("w:p")

    def _walk(container: Any) -> None:
        for p_el in container.iter(p_tag):
            _cleanup_word_if_fields_in_paragraph_element(p_el)
            _replace_mergefields_in_paragraph_element(p_el, field_map)
            _cleanup_word_field_markup_in_paragraph_element(p_el)
            _normalize_merge_code_paragraph_element(p_el)

    _walk(doc.element.body)
    for section in doc.sections:
        for hf in (
            section.header,
            section.footer,
            section.even_page_header,
            section.even_page_footer,
            section.first_page_header,
            section.first_page_footer,
        ):
            _walk(hf._element)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _merge_precedent_codes_in_ooxml_zip(src_bytes: bytes, fields: dict[str, str]) -> bytes:
    """Replace ``[CODE]`` substrings in raw OOXML parts (one pass per file).

    Runs **after** the python-docx paragraph pass. Catches any remaining contiguous
    placeholders in XML (including footnotes) and tokens split across ``<w:t>`` boundaries
    that the paragraph walk could not join for ``and`` insertion.
    """
    import io
    import zipfile

    escaped = {k: _xml_escape_ooxml_text(v) for k, v in fields.items()}
    src = io.BytesIO(src_bytes)
    out = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            raw = zin.read(info.filename)
            if _ooxml_part_path_matches(info.filename):
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(info, raw)
                    continue
                text = _replace_merge_tokens_in_ooxml_text(text, escaped)
                raw = text.encode("utf-8")
            zout.writestr(info, raw)
    return out.getvalue()


def _replace_merge_tokens_in_ooxml_text(text: str, fields: Mapping[str, str]) -> str:
    """Replace merge tokens in raw OOXML text (modifiers are dropped — plain escaped value)."""

    def repl(m: re.Match[str]) -> str:
        key = f"[{m.group(2).upper()}]"
        if key not in fields:
            return m.group(0)
        return fields[key]

    return _MERGE_TOKEN_RE.sub(repl, text)


def _rewrite_paragraph_to_runs(para: Any, segments: list[_MergeTextSegment]) -> None:
    """Replace paragraph content with formatted runs (supports embedded ``\\n`` as line breaks)."""
    from docx.enum.text import WD_BREAK
    from docx.oxml.ns import qn

    def _apply_run_formatting(run: Any, seg: _MergeTextSegment) -> None:
        if seg.bold is not None:
            run.bold = seg.bold
        if seg.italic is not None:
            run.italic = seg.italic
        if seg.underline is not None:
            run.underline = seg.underline

    p_el = para._p
    for child in list(p_el):
        if child.tag != qn("w:pPr"):
            p_el.remove(child)
    for seg in segments:
        if not seg.text:
            continue
        has_fmt = seg.bold is not None or seg.italic is not None or seg.underline is not None
        lines = seg.text.split("\n")
        if has_fmt and len(lines) > 1:
            run = para.add_run(lines[0])
            _apply_run_formatting(run, seg)
            for line in lines[1:]:
                run.add_break(WD_BREAK.LINE)
                if line:
                    run.add_text(line)
            continue
        for i, part in enumerate(lines):
            if i > 0:
                br_run = para.add_run()
                br_run.add_break(WD_BREAK.LINE)
                if has_fmt:
                    _apply_run_formatting(br_run, seg)
            if not part:
                continue
            run = para.add_run(part)
            _apply_run_formatting(run, seg)


def _rewrite_paragraph_to_single_run(para: Any, replaced: str) -> None:
    """Replace paragraph content with plain text (supports embedded ``\\n`` as Word line breaks).

    Word often puts merge tokens in hyperlinked or oddly split runs. Clearing only ``para.runs``
    can leave ``w:hyperlink`` / nested ``w:t`` behind, so the old token still appears next to
    the merged text (e.g. surname twice with a gap). We strip non-``w:pPr`` children and add
    fresh runs — same approach as a clean retype of the paragraph.
    """
    from docx.enum.text import WD_BREAK
    from docx.oxml.ns import qn

    p_el = para._p
    for child in list(p_el):
        if child.tag != qn("w:pPr"):
            p_el.remove(child)
    parts = replaced.split("\n")
    for i, part in enumerate(parts):
        if i > 0:
            para.add_run().add_break(WD_BREAK.LINE)
        para.add_run(part)

def _coalesce_split_merge_tokens_in_docx(doc_bytes: bytes) -> bytes:
    """Join ``w:r`` text when ONLYOFFICE/Word split a merge token across runs inside one paragraph.

    Only the runs that participate in a split token are merged into one run; other runs (e.g. a bold
    ``Re:`` prefix) are left intact so formatting survives into :func:`merge_precedent_codes`.
    """
    import io
    from copy import deepcopy

    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(doc_bytes))
    t_tag = qn("w:t")
    r_tag = qn("w:r")
    changed = False

    def _run_plain_text(r_el: Any) -> str:
        return "".join(t.text or "" for t in r_el.iter(t_tag))

    def _make_plain_text_run(p_el: Any, text: str) -> Any:
        r = p_el.makeelement(r_tag, {})
        attrs = {qn("xml:space"): "preserve"} if text.strip() != text else {}
        t = p_el.makeelement(t_tag, attrs)
        t.text = text
        r.append(t)
        return r

    def _clone_run_with_text(p_el: Any, template_el: Any, text: str) -> Any:
        if not text:
            return None
        r = deepcopy(template_el)
        for child in list(r):
            r.remove(child)
        attrs = {qn("xml:space"): "preserve"} if text.strip() != text else {}
        t = p_el.makeelement(t_tag, attrs)
        t.text = text
        r.append(t)
        return r

    def _run_infos(p_el: Any) -> list[dict[str, Any]]:
        infos: list[dict[str, Any]] = []
        pos = 0
        for r_el in p_el.findall(r_tag):
            text = _run_plain_text(r_el)
            infos.append({"el": r_el, "text": text, "start": pos, "end": pos + len(text)})
            pos += len(text)
        return infos

    def _split_tokens_in_paragraph(infos: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
        combined = "".join(ri["text"] for ri in infos)
        if not combined or not _MERGE_TOKEN_RE.search(combined):
            return []
        out: list[tuple[int, int, str]] = []
        for m in _MERGE_TOKEN_RE.finditer(combined):
            token = m.group(0)
            if not any(token in ri["text"] for ri in infos if ri["text"]):
                out.append((m.start(), m.end(), token))
        return out

    def _coalesce_p(p_el: Any) -> None:
        nonlocal changed
        infos = _run_infos(p_el)
        if not infos:
            return
        split_tokens = _split_tokens_in_paragraph(infos)
        if not split_tokens:
            return

        out_runs: list[Any] = []
        pending = list(infos)
        combined = "".join(ri["text"] for ri in infos)
        for ts, te, _token in split_tokens:
            next_pending: list[dict[str, Any]] = []
            token_emitted = False
            carry_suffix: list[dict[str, Any]] = []
            for ri in pending:
                if ri["end"] <= ts:
                    out_runs.append(deepcopy(ri["el"]))
                elif ri["start"] >= te:
                    next_pending.append(ri)
                else:
                    if ri["start"] < ts:
                        prefix = _clone_run_with_text(p_el, ri["el"], combined[ri["start"] : ts])
                        if prefix is not None:
                            out_runs.append(prefix)
                    if not token_emitted:
                        out_runs.append(_make_plain_text_run(p_el, combined[ts:te]))
                        token_emitted = True
                    if ri["end"] > te:
                        carry_suffix.append(
                            {
                                "el": ri["el"],
                                "text": combined[te : ri["end"]],
                                "start": te,
                                "end": ri["end"],
                            }
                        )
            pending = carry_suffix + next_pending

        for ri in pending:
            if _run_plain_text(ri["el"]) == ri["text"]:
                out_runs.append(deepcopy(ri["el"]))
            else:
                cloned = _clone_run_with_text(p_el, ri["el"], ri["text"])
                if cloned is not None:
                    out_runs.append(cloned)

        for r in list(p_el.findall(r_tag)):
            p_el.remove(r)
        for r in out_runs:
            p_el.append(r)
        changed = True

    def _walk_paragraphs(container: Any) -> None:
        for p_el in container.iter(qn("w:p")):
            _coalesce_p(p_el)

    _walk_paragraphs(doc.element.body)
    for section in doc.sections:
        for hf in (
            section.header,
            section.footer,
            section.even_page_header,
            section.even_page_footer,
            section.first_page_header,
            section.first_page_footer,
        ):
            _walk_paragraphs(hf._element)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                _walk_paragraphs(cell._tc)

    if not changed:
        return doc_bytes
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def merge_precedent_codes(
    src_bytes: bytes,
    fields: dict[str, str],
    *,
    ordered_clients: list[Any] | None = None,
    merge_all_clients: bool = False,
) -> bytes:
    """Replace [CODE] placeholders in a .docx (precedent merge).

    1. **python-docx paragraph pass** — when ``merge_all_clients`` is true, inserts the word
       ``and`` between adjacent client name placeholders for consecutive clients that both
       have name/company data; then substitutes fields; handles merged table cells; removes
       code-only blank paragraphs.

    2. **Zip / OOXML pass** — replaces any remaining contiguous ``[CODE]`` or
       ``[modifiers:CODE]`` substrings in document parts (including split tokens not fixed
       in step 1; formatting modifiers may be lost when a token was split across XML nodes).

    Image merge codes (``IMAGE_PRECEDENT_CODES``) are left in the document for
    ``inject_merge_code_images`` to replace with inline pictures.
    """
    text_fields = {k: v for k, v in fields.items() if k not in IMAGE_PRECEDENT_CODES}
    sep_flags = _inter_client_sep_flags(ordered_clients) if merge_all_clients else {}
    prepared = _coalesce_split_merge_tokens_in_docx(src_bytes)
    merged = _merge_precedent_codes_via_python_docx(prepared, text_fields, sep_flags)
    return _merge_precedent_codes_in_ooxml_zip(merged, text_fields)


def fee_earner_signature_image_path(db: Session, user_id: uuid.UUID | None) -> Path | None:
    info = fee_earner_signature_for_merge(db, user_id)
    return info[0] if info else None


SIGNATURE_SCALE_DEFAULT = 7
SIGNATURE_WIDTH_INCHES_AT_DEFAULT_SCALE = 2.0


def signature_width_inches_from_scale(scale: int | None) -> float:
    """Map user signature scale 1–10 to width in inches (7 → 2.0 in)."""
    s = SIGNATURE_SCALE_DEFAULT if scale is None else max(1, min(10, int(scale)))
    return SIGNATURE_WIDTH_INCHES_AT_DEFAULT_SCALE * s / SIGNATURE_SCALE_DEFAULT


def fee_earner_signature_for_merge(
    db: Session,
    user_id: uuid.UUID | None,
) -> tuple[Path, float] | None:
    from app.file_storage import FILES_ROOT
    from app.models import File, FirmSettings, User

    def _resolve_file(*, file_id: uuid.UUID | None, scale: int | None) -> tuple[Path, float] | None:
        if not file_id:
            return None
        row = db.get(File, file_id)
        if not row:
            return None
        abs_path = (FILES_ROOT / row.storage_path).resolve()
        if not abs_path.is_file():
            return None
        width = signature_width_inches_from_scale(scale)
        return abs_path, width

    if user_id:
        user = db.get(User, user_id)
        if user and user.signature_file_id:
            info = _resolve_file(file_id=user.signature_file_id, scale=getattr(user, "signature_scale", None))
            if info:
                return info

    firm = db.get(FirmSettings, 1)
    if firm and firm.default_signature_file_id:
        return _resolve_file(
            file_id=firm.default_signature_file_id,
            scale=getattr(firm, "default_signature_scale", SIGNATURE_SCALE_DEFAULT),
        )
    return None


def _normalized_merge_paragraph_text(text: str | None) -> str:
    return (text or "").replace("\u200b", "").replace("\xa0", " ").strip()


def inject_merge_code_images(
    src_bytes: bytes,
    images: dict[str, Path],
    *,
    width_inches: Mapping[str, float] | None = None,
) -> bytes:
    """Replace image merge-code paragraphs with inline pictures (paragraph must contain only the code)."""
    if not images:
        return src_bytes
    import io
    from docx import Document
    from docx.shared import Inches

    widths = width_inches or {}
    src_bytes = _coalesce_split_merge_tokens_in_docx(src_bytes)
    doc = Document(io.BytesIO(src_bytes))
    changed = False

    def _walk_paragraph(para: Any) -> None:
        nonlocal changed
        text = _normalized_merge_paragraph_text(para.text)
        for code, img_path in images.items():
            if text != code or not img_path.is_file():
                continue
            para.clear()
            run = para.add_run()
            w = widths.get(code, SIGNATURE_WIDTH_INCHES_AT_DEFAULT_SCALE)
            run.add_picture(str(img_path), width=Inches(w))
            changed = True
            return

    for para in doc.paragraphs:
        _walk_paragraph(para)
    for section in doc.sections:
        for hf in (
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ):
            for para in hf.paragraphs:
                _walk_paragraph(para)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _walk_paragraph(para)
    if not changed:
        return src_bytes
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _merge_precedent_codes_via_python_docx(
    src_bytes: bytes,
    fields: dict[str, str],
    sep_flags: dict[tuple[int, int], bool],
) -> bytes:
    """Paragraph walk: optional *and* insertion, field replace, blank-line cleanup."""
    import io
    from docx import Document

    doc = Document(io.BytesIO(src_bytes))

    seen_wp: set[Any] = set()

    def _merge_para(para: Any) -> bool:
        """Merge codes in para. Returns True if the para should be removed (became blank)."""
        wp = para._p
        if wp in seen_wp:
            return False
        # Read run-level formatting before flattening so static bold/italic survives merge.
        segments = _paragraph_to_formatted_segments(para)
        full = _segments_plain_text(segments)
        if not full:
            return False  # already empty — don't touch
        if sep_flags:
            segments = _insert_and_between_adjacent_name_placeholders_in_segments(segments, sep_flags)
            full = _segments_plain_text(segments)
        if not _paragraph_has_merge_tokens(full, fields):
            return False
        # Claim only once we will rewrite, so empty / no-code paragraphs visited from duplicate
        # merged cells can still be processed on a later distinct visit (should not happen, but safe).
        seen_wp.add(wp)
        had_modifier_tokens = _paragraph_has_modifier_tokens(full)
        segments = _replace_merge_tokens_in_formatted_segments(segments, fields)
        if _segments_have_direct_formatting(segments) or had_modifier_tokens:
            segments = _trim_leading_segment_whitespace(segments)
            replaced = _normalize_post_merge_whitespace(_segments_plain_text(segments))
            _rewrite_paragraph_to_runs(para, segments)
        else:
            replaced = _normalize_post_merge_whitespace(_segments_plain_text(segments))
            _rewrite_paragraph_to_single_run(para, replaced)
        # Remove the paragraph if it's now blank (was code-only, value was empty)
        return not replaced.strip()

    def _process_paras(paras: Any) -> None:
        plist = list(paras) if not isinstance(paras, list) else paras
        to_remove = [p for p in plist if _merge_para(p)]
        for p in to_remove:
            p._element.getparent().remove(p._element)

    def _iter_distinct_cells(table: Any):
        """Each physical cell once (merged cells share one ``w:tc`` but span multiple grid slots)."""
        seen_tc: set[Any] = set()
        for row in table.rows:
            for cell in row.cells:
                tc = cell._tc
                if tc in seen_tc:
                    continue
                seen_tc.add(tc)
                yield cell

    def _process_table(table: Any) -> None:
        for cell in _iter_distinct_cells(table):
            _process_paras(cell.paragraphs)
            nested = getattr(cell, "tables", None)
            if nested:
                for nt in nested:
                    _process_table(nt)

    # Body paragraphs (not inside tables)
    _process_paras(doc.paragraphs)

    for table in doc.tables:
        _process_table(table)

    # Headers / footers
    for section in doc.sections:
        for hf in (section.header, section.footer,
                   section.even_page_header, section.even_page_footer,
                   section.first_page_header, section.first_page_footer):
            if hf.is_linked_to_previous:
                continue
            _process_paras(hf.paragraphs)
            for table in hf.tables:
                _process_table(table)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

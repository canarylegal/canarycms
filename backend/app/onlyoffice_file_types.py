"""ONLYOFFICE document type sniffing and editor permission defaults."""

from __future__ import annotations

import logging
from pathlib import Path

from app.feature_flags import onlyoffice_pdf_editor_types, open_pdf_in_onlyoffice

log = logging.getLogger(__name__)

# document.permissions: keep booleans only — nested commentGroups/reviewGroups shapes have caused
# "token not correctly formed" / blank editor on some Document Server versions.
_ONLYOFFICE_DOC_PERMISSIONS: dict[str, bool] = {
    "comment": True,
    "copy": True,
    "download": True,
    "edit": True,
    "fillForms": True,
    "modifyContentControl": True,
    "modifyFilter": True,
    # Hide DS File → Print (Firefox treats /printfile/… PDF as download handler). Canary Print uses
    # downloadAs('pdf') + /onlyoffice/print-ui instead; keep download: True for that pipeline.
    "print": False,
    "review": True,
}


def _onlyoffice_types_for_file(original_filename: str) -> tuple[str, str] | None:
    """Return (documentType, fileType) for ONLYOFFICE, or None if unsupported."""
    ext = Path(original_filename).suffix.lower().lstrip(".")
    if ext in {"doc", "docx", "dot", "dotx", "odt", "rtf", "txt"}:
        return ("word", ext)
    if ext in {"xls", "xlsx", "xlsm", "xlsb", "ods"}:
        return ("cell", ext)
    if ext in {"ppt", "pptx", "pps", "ppsx", "odp"}:
        return ("slide", ext)
    if open_pdf_in_onlyoffice() and ext == "pdf":
        return onlyoffice_pdf_editor_types()
    return None


# Old binary formats that share an extension with their newer OOXML equivalents.
# If the file starts with the ZIP magic (PK\x03\x04), the actual format is the OOXML variant.
_OOXML_UPGRADE: dict[str, str] = {"doc": "docx", "dot": "dotx", "xls": "xlsx", "ppt": "pptx", "pps": "ppsx"}
_ZIP_MAGIC = b"PK\x03\x04"


def _correct_file_type(file_type: str, abs_path: Path) -> str:
    """Return the real fileType by sniffing magic bytes when the extension claims an old binary format.

    Files uploaded with a .DOC/.XLS/.PPT extension are sometimes actually OOXML/ZIP files (e.g. Word
    2007+ saved-as .doc). ONLYOFFICE reports 'download failed' if told to parse ZIP bytes as OLE2.
    """
    new_type = _OOXML_UPGRADE.get(file_type)
    if new_type is None:
        return file_type
    try:
        with abs_path.open("rb") as fh:
            magic = fh.read(4)
        if magic == _ZIP_MAGIC:
            log.info("_correct_file_type: %s is ZIP/OOXML — using fileType %r instead of %r", abs_path.name, new_type, file_type)
            return new_type
    except OSError:
        pass
    return file_type

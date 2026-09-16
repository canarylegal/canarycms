"""EML/MSG parse helpers and mail metadata refresh for case file uploads."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from fastapi import HTTPException, status

from app.file_storage import StoredFilePaths, case_file_paths
from app.models import File as DbFile

log = logging.getLogger(__name__)


def _unfold_rfc822_header_block(header_b: bytes) -> list[str]:
    """Folded header lines (leading FWS) join to the previous field."""
    text = header_b.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and out:
            out[-1] = (out[-1].rstrip() + " " + line.strip()).strip()
        else:
            out.append(line.rstrip())
    return out


def _decode_header_value(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _eml_parse_message_id_from_header(abs_path: Path) -> str | None:
    """Read Message-ID / Message-Id from the first chunk of a .eml / message/rfc822 file."""
    try:
        with abs_path.open("rb") as fh:
            raw = fh.read(131072)
        if not raw.strip():
            return None
        while raw.startswith(b"From ") and b"\n" in raw:
            raw = raw.split(b"\n", 1)[1]
        if b"\r\n\r\n" in raw:
            header = raw.split(b"\r\n\r\n", 1)[0]
        elif b"\n\n" in raw:
            header = raw.split(b"\n\n", 1)[0]
        else:
            header = raw
        if not header.strip():
            return None
        for line in _unfold_rfc822_header_block(header):
            m = re.match(r"(?i)^message-id\s*:\s*(.*)$", line)
            if not m:
                continue
            val = (m.group(1) or "").strip()
            return val if val else None
        msg = message_from_bytes(header + b"\n\n")
        mid = msg.get("Message-ID") or msg.get("Message-Id")
        if mid:
            s = str(mid).strip()
            return s if s else None
        return None
    except Exception:
        return None


def _eml_parse_from_header(abs_path: Path) -> tuple[str | None, str | None]:
    """Read From: from the first chunk of a .eml / message/rfc822 file (uploaded parent only)."""
    try:
        with abs_path.open("rb") as fh:
            raw = fh.read(131072)
        if not raw.strip():
            return None, None
        # Strip leading "From " mbox separator lines (unlikely but defensive).
        while raw.startswith(b"From ") and b"\n" in raw:
            raw = raw.split(b"\n", 1)[1]
        if b"\r\n\r\n" in raw:
            header = raw.split(b"\r\n\r\n", 1)[0]
        elif b"\n\n" in raw:
            header = raw.split(b"\n\n", 1)[0]
        else:
            header = raw
        if not header.strip():
            return None, None

        for line in _unfold_rfc822_header_block(header):
            m = re.match(r"(?i)^from\s*:\s*(.*)$", line)
            if not m:
                continue
            raw_val = (m.group(1) or "").strip()
            if not raw_val:
                continue
            decoded = _decode_header_value(raw_val)
            name, addr = parseaddr(decoded)
            n = name.strip() if name else ""
            a = addr.strip() if addr else ""
            if n or a:
                return (n or None, a or None)

        msg = message_from_bytes(header + b"\n\n")
        from_val = msg.get("From")
        if from_val:
            decoded = _decode_header_value(str(from_val))
            name, addr = parseaddr(decoded)
            n = name.strip() if name else ""
            a = addr.strip() if addr else ""
            if n or a:
                return (n or None, a or None)
        return None, None
    except Exception:
        return None, None


def _eml_parse_date_header(abs_path: Path) -> datetime | None:
    """Read Date: from the first chunk of a .eml / message/rfc822 file; return UTC-aware datetime or None."""
    try:
        with abs_path.open("rb") as fh:
            raw = fh.read(131072)
        if not raw.strip():
            return None
        while raw.startswith(b"From ") and b"\n" in raw:
            raw = raw.split(b"\n", 1)[1]
        if b"\r\n\r\n" in raw:
            header = raw.split(b"\r\n\r\n", 1)[0]
        elif b"\n\n" in raw:
            header = raw.split(b"\n\n", 1)[0]
        else:
            header = raw
        if not header.strip():
            return None
        msg = message_from_bytes(header + b"\n\n")
        raw_date = msg.get("Date")
        if not raw_date:
            return None
        dt = parsedate_to_datetime(str(raw_date))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def _imap_mbox_implies_outbound(mbox: str | None) -> bool | None:
    """Return True/False when the IMAP folder name reliably indicates sent vs inbox; else None."""
    if not mbox or not str(mbox).strip():
        return None
    s = str(mbox).replace("\\", "/").lower()
    if "draft" in s:
        return None
    if "unsent" in s:
        return False
    if "outbox" in s or "sent" in s:
        return True
    return None


def _infer_source_mail_is_outbound(
    mbox: str | None,
    from_email: str | None,
    uploader_email: str | None,
) -> bool | None:
    by_mbox = _imap_mbox_implies_outbound(mbox)
    if by_mbox is not None:
        return by_mbox
    fe = (from_email or "").strip().lower()
    ue = (uploader_email or "").strip().lower()
    if fe and ue and fe == ue:
        return True
    return None


def convert_case_upload_msg_to_eml_if_applicable(
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    folder_path: str,
    original_filename: str,
    paths: StoredFilePaths,
) -> tuple[str, StoredFilePaths, int]:
    """If ``original_filename`` ends with ``.msg``, replace file on disk with RFC822 ``.eml`` content."""
    if not original_filename.lower().endswith(".msg"):
        return original_filename, paths, paths.abs_path.stat().st_size

    from app.outlook_msg import outlook_msg_path_to_eml_bytes

    try:
        eml_bytes = outlook_msg_path_to_eml_bytes(paths.abs_path)
    except Exception as exc:
        log.exception("MSG→EML conversion failed during upload")
        paths.abs_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not convert Outlook .msg to e-mail (.eml). The file may be corrupt or not an Outlook message.",
        ) from exc
    paths.abs_path.unlink(missing_ok=True)
    eml_name = f"{Path(original_filename).stem}.eml"
    new_paths = case_file_paths(
        case_id=case_id,
        file_id=file_id,
        original_filename=eml_name,
        folder_path=folder_path,
    )
    new_paths.abs_path.write_bytes(eml_bytes)
    return eml_name, new_paths, len(eml_bytes)


def _row_is_eml_like(row: DbFile) -> bool:
    name = (row.original_filename or "").lower()
    mime = (row.mime_type or "").lower()
    return bool(
        name.endswith(".eml")
        or "message/rfc822" in mime
        or "rfc822" in mime
    )


def refresh_root_eml_mail_metadata(frow: DbFile, abs_path: Path, *, uploader_email: str | None) -> None:
    """Re-parse From: etc. for a root (non-attachment) ``.eml`` after the file on disk changed."""
    if frow.parent_file_id is not None:
        return
    low = (frow.original_filename or "").lower()
    mime = (frow.mime_type or "").lower()
    if not low.endswith(".eml") and "message/rfc822" not in mime:
        return
    fn, fe = _eml_parse_from_header(abs_path)
    frow.source_mail_from_name = fn
    frow.source_mail_from_email = fe
    frow.source_mail_is_outbound = _infer_source_mail_is_outbound(frow.source_imap_mbox, fe, uploader_email)
    frow.source_internet_message_id = _eml_parse_message_id_from_header(abs_path)
    frow.source_mail_date = _eml_parse_date_header(abs_path)

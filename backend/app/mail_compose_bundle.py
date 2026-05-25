"""Build mail-client compose bundles (merge + attachments) for Thunderbird and handoff tokens."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.deps import require_case_access
from app.file_storage import FILES_ROOT, ensure_files_root
from app.models import File as DbFile
from app.models import User
from app.routers.files import _case_email_compose_bundle
from app.schemas import (
    CaseEmailDraftM365In,
    MailPluginComposeAttachmentOut,
    MailPluginComposeHandoffOut,
)


def encode_compose_attachments(
    db: Session,
    case_id: uuid.UUID,
    user: User,
    attachment_file_ids: list[uuid.UUID],
) -> list[MailPluginComposeAttachmentOut]:
    require_case_access(case_id, user, db)
    ensure_files_root()
    out: list[MailPluginComposeAttachmentOut] = []
    for fid in attachment_file_ids:
        frow = db.get(DbFile, fid)
        if not frow or frow.case_id != case_id:
            continue
        abs_p = (FILES_ROOT / frow.storage_path).resolve()
        if not str(abs_p).startswith(str(FILES_ROOT)) or not abs_p.is_file():
            continue
        raw = abs_p.read_bytes()
        if len(raw) > 100 * 1024 * 1024:
            continue
        fn = Path(frow.original_filename).name or "attachment"
        mt = frow.mime_type or "application/octet-stream"
        out.append(
            MailPluginComposeAttachmentOut(
                file_id=fid,
                filename=fn,
                mime_type=mt,
                content_base64=base64.b64encode(raw).decode("ascii"),
            )
        )
    return out


def build_mail_compose_bundle(
    db: Session,
    case_id: uuid.UUID,
    body: CaseEmailDraftM365In,
    user: User,
) -> MailPluginComposeHandoffOut:
    require_case_access(case_id, user, db)
    to_addr, subject, body_text, _raw_attachments = _case_email_compose_bundle(case_id, body, user, db)
    attachments = encode_compose_attachments(db, case_id, user, body.attachment_file_ids)
    return MailPluginComposeHandoffOut(
        case_id=case_id,
        to=to_addr,
        subject=subject,
        body=body_text,
        attachments=attachments,
    )

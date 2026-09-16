"""Case e-mail compose helpers (M365 draft, mailto, Thunderbird handoff merge)."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.compose_merge import merge_compose_docx_bytes, resolve_blank_email_compose_body
from app.deps import require_case_access
from app.docx_util import extract_plain_text_from_docx_bytes
from app.file_storage import FILES_ROOT, ensure_files_root, path_is_under_files_root
from app.graph_mail import create_outlook_draft, graph_mail_configured
from app.models import Case as CaseRow
from app.models import CaseContact, Contact as GlobalContactRow
from app.models import File as DbFile, FileCategory, PrecedentKind, User
from app.schemas import (
    CaseEmailDraftM365AttachmentOut,
    CaseEmailDraftM365In,
    CaseEmailDraftM365Out,
    ComposeOfficeDocumentIn,
)
from app.security import create_compose_handoff_token

log = logging.getLogger(__name__)


def _resolve_recipient_email_m365(
    db: Session,
    case_id: uuid.UUID,
    body: ComposeOfficeDocumentIn,
) -> str:
    """To: address for the Graph draft. Empty string omits toRecipients; user fills To in Outlook."""
    if body.precedent_merge_all_clients:
        return ""
    if body.case_contact_id:
        cc = db.get(CaseContact, body.case_contact_id)
        if not cc or cc.case_id != case_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter contact not found")
        addr = (cc.email or "").strip()
        if not addr and cc.contact_id:
            master = db.get(GlobalContactRow, cc.contact_id)
            if master and master.email:
                addr = master.email.strip()
        return addr
    if body.global_contact_id:
        g = db.get(GlobalContactRow, body.global_contact_id)
        if not g:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
        return (g.email or "").strip() if g.email else ""
    return ""


def _case_email_compose_bundle(
    case_id: uuid.UUID,
    body: CaseEmailDraftM365In,
    user: User,
    db: Session,
) -> tuple[str, str, str, list[tuple[str, str, bytes]]]:
    """Shared merge + attachments for M365 draft and mailto compose."""
    merge_in = ComposeOfficeDocumentIn(
        original_filename="Email draft.docx",
        folder=body.folder or "",
        precedent_id=body.precedent_id,
        case_contact_id=body.case_contact_id,
        global_contact_id=body.global_contact_id,
        precedent_merge_all_clients=body.precedent_merge_all_clients,
        compose_office_role=None,
    )
    merge_in = resolve_blank_email_compose_body(db, merge_in)
    kind_filter = PrecedentKind.email if merge_in.precedent_id is not None else None
    src_bytes, _mime = merge_compose_docx_bytes(db, case_id, merge_in, require_precedent_kind=kind_filter)
    body_text = extract_plain_text_from_docx_bytes(src_bytes)
    if not body_text.strip():
        body_text = " "

    to_addr = _resolve_recipient_email_m365(db, case_id, merge_in)

    contact_ref = ""
    if body.case_contact_id and not body.precedent_merge_all_clients:
        cc_subj = db.get(CaseContact, body.case_contact_id)
        if cc_subj and cc_subj.case_id == case_id:
            contact_ref = (cc_subj.matter_contact_reference or "").strip()
    case_row = db.get(CaseRow, case_id)
    subject_bits: list[str] = []
    if case_row and (case_row.title or "").strip():
        subject_bits.append(case_row.title.strip())
    if contact_ref:
        subject_bits.append(contact_ref)
    subject = " — ".join(subject_bits) if subject_bits else "E-mail"

    attachments: list[tuple[str, str, bytes]] = []
    if len(body.attachment_file_ids) > 25:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At most 25 attachments.")
    ensure_files_root()
    for fid in body.attachment_file_ids:
        frow = db.get(DbFile, fid)
        if not frow or frow.case_id != case_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Attachment file not found: {fid}")
        if frow.category == FileCategory.system:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot attach system items.")
        abs_p = (FILES_ROOT / frow.storage_path).resolve()
        if not path_is_under_files_root(abs_p) or not abs_p.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file missing on disk")
        raw = abs_p.read_bytes()
        if len(raw) > 100 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Attachment too large: {frow.original_filename}",
            )
        fn = Path(frow.original_filename).name or "attachment"
        mt = frow.mime_type or mimetypes.guess_type(fn)[0] or "application/octet-stream"
        attachments.append((fn, mt, raw))

    return to_addr, subject, body_text, attachments


def _create_case_email_draft_m365_body(
    case_id: uuid.UUID,
    body: CaseEmailDraftM365In,
    user: User,
    db: Session,
) -> CaseEmailDraftM365Out:
    require_case_access(case_id, user, db)
    if not graph_mail_configured(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Microsoft 365 e-mail drafts are not configured. An admin must set **Microsoft 365 (Entra / Graph)** "
                "in Admin settings → E-mail (or set CANARY_MS_GRAPH_* in the server environment), "
                "and grant Mail.ReadWrite (application) admin consent."
            ),
        )
    mailbox = (user.email or "").strip()
    if not mailbox:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your Canary account must have an e-mail address that matches the Microsoft 365 mailbox to use.",
        )

    to_addr, subject, body_text, attachments = _case_email_compose_bundle(case_id, body, user, db)

    try:
        primary, draft_id, compose_extra, _imid, prefill_url = create_outlook_draft(
            mailbox,
            to_addr=to_addr,
            subject=subject,
            body_text=body_text,
            attachments=attachments,
            db=db,
            mailbox_user_row=user,
        )
    except RuntimeError as e:
        msg = str(e)
        log.warning("Graph draft failed: %s", msg)
        # Avoid HTTP 502 for Graph auth/ACL failures — some CDNs replace the JSON body with an HTML error page.
        if "Microsoft Graph token request failed (401)" in msg or "invalid_client" in msg:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg) from e
        if "Microsoft Graph draft create failed (403)" in msg or "ErrorAccessDenied" in msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Microsoft Graph refused to create the draft (access denied). "
                    "In Entra ID → your app → API permissions: add **Mail.ReadWrite** under **Application** "
                    "(not Delegated), then **Grant admin consent** for the tenant. "
                    "The Canary account email must be an Exchange Online mailbox in that same tenant. "
                    f"Upstream detail: {msg[:900]}"
                ),
            ) from e
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg) from e
    except Exception as e:
        log.exception("M365 draft failed with unexpected error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected error while creating the Outlook draft: {e}",
        ) from e

    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.email_draft_m365",
        entity_type="graph_message",
        entity_id=draft_id,
        meta={
            "case_id": str(case_id),
            "graph_message_id": draft_id,
            "precedent_id": str(body.precedent_id) if body.precedent_id else None,
            "attachment_count": len(body.attachment_file_ids),
        },
    )
    handoff_token: str | None = None
    attachment_files_out: list[CaseEmailDraftM365AttachmentOut] = []
    if attachments:
        handoff_token = create_compose_handoff_token(
            user_id=str(user.id),
            case_id=str(case_id),
            to=to_addr,
            subject=subject,
            body=body_text,
            attachment_file_ids=[str(fid) for fid in body.attachment_file_ids],
        )
        for fid in body.attachment_file_ids:
            frow = db.get(DbFile, fid)
            if frow and frow.case_id == case_id:
                attachment_files_out.append(
                    CaseEmailDraftM365AttachmentOut(
                        file_id=fid,
                        filename=Path(frow.original_filename).name or "attachment",
                    ),
                )

    return CaseEmailDraftM365Out(
        to=to_addr,
        subject=subject,
        body=body_text,
        open_url=primary,
        graph_message_id=draft_id,
        draft_compose_web_link=compose_extra,
        compose_prefill_url=prefill_url,
        attachment_count=len(attachments),
        compose_handoff_token=handoff_token,
        attachment_files=attachment_files_out,
    )

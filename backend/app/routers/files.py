import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, Query, Request, Response, UploadFile, status, Form
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.file_storage import FILES_ROOT, ensure_files_root, path_is_under_files_root
from app.file_eml_service import (
    refresh_root_eml_mail_metadata,
    _row_is_eml_like,
)
# Re-exported for tests (e.g. test_folder_upload_delete_race).
from app.case_folder_service import (  # noqa: F401
    _FOLDER_GONE_DETAIL,
    _FOLDER_MODIFIED_DURING_DELETE_DETAIL,
    _as_utc,
    _folder_destination_exists,
    _prepare_upload_folder,
    _try_lock_case_folder_ops_session,
    _unlock_case_folder_ops_session,
    create_case_folder as create_case_folder_service,
    delete_case_folder as delete_case_folder_service,
    move_case_folder as move_case_folder_service,
    rename_case_folder as rename_case_folder_service,
)
from app.case_email_compose_service import (
    _case_email_compose_bundle,
    _create_case_email_draft_m365_body,
)
from app.case_file_export_service import (
    download_case_export_zip as download_case_export_zip_service,
    download_case_folder_zip as download_case_folder_zip_service,
)
from app.case_file_mutate_service import (
    _FILE_RENAME_CONFLICT_DETAIL,  # noqa: F401
    delete_case_file as delete_case_file_service,
    move_case_file as move_case_file_service,
    rename_case_file as rename_case_file_service,
    set_file_pin as set_file_pin_service,
    update_comment_file as update_comment_file_service,
)
from app.file_upload_service import (
    compose_office_document as compose_office_document_service,
    compose_quote_spreadsheet as compose_quote_spreadsheet_service,
    upload_case_file as upload_case_file_service,
)
# Re-exported for tests (e.g. test_feature_flags).
from app.onlyoffice_file_types import (  # noqa: F401
    _ONLYOFFICE_DOC_PERMISSIONS,
    _correct_file_type,
    _onlyoffice_types_for_file,
)
from app.onlyoffice_case_file_service import (
    _onlyoffice_cli_hint,  # noqa: F401
    _redact_webdav_url_for_log,  # noqa: F401
    checkout_desktop_edit as checkout_desktop_edit_service,
    discard_onlyoffice_edit as discard_onlyoffice_edit_service,
    get_desktop_edit_session as get_desktop_edit_session_service,
    get_onlyoffice_editor_config as get_onlyoffice_editor_config_service,
    oo_export_pdf as oo_export_pdf_service,
    oo_force_save as oo_force_save_service,
    oo_persist_download as oo_persist_download_service,
    oo_save_status as oo_save_status_service,
    publish_compose_office_file as publish_compose_office_file_service,
    release_desktop_edit as release_desktop_edit_service,
)
from app.upload_limits import content_disposition_for_mime
from app.models import Contact as GlobalContactRow, ContactPortalGrant
from app.models import File as DbFile, User
from app.portal_service import grant_is_client_visible
from app.portal_case import require_case_portal_enabled
from app.audit import log_event
from app.onlyoffice_force_save import OoForceSavePhase
from app.graph_outbound_service import repair_outlook_web_link_on_file
from app.owa_urls import outlook_graph_message_id_storable as _outlook_graph_message_id_storable
from app.security import (
    COMPOSE_HANDOFF_TTL_SECONDS,
    create_compose_handoff_token,
    create_eml_open_token,
    decode_compose_handoff_token,
    decode_eml_open_token,
)
from app.schemas import (
    CaseFileMoveUpdate,
    CaseFileRenameUpdate,
    CaseFolderCreate,
    CaseFolderDeleteUpdate,
    CaseFolderMoveUpdate,
    CaseFolderRenameUpdate,
    CasePortalFolderAccessGrantOut,
    CaseEmailDraftM365In,
    CaseEmailDraftM365Out,
    CaseEmailComposeHandoffOut,
    CaseEmailMailtoOut,
    CommentFileUpdate,
    ComposeOfficeDocumentIn,
    ComposeQuoteIn,
    FileDesktopCheckoutOut,
    FileEditSessionStatusOut,
    FilePinUpdate,
    OnlyofficeEditorConfigOut,
    OoExportPdfIn,
    OoExportPdfOut,
    OoPersistDownloadIn,
    OutlookOpenHintsOut,
    PortalQuoteTagUpdate,
    PublishComposeIn,
)
from app.quote_portal_service import set_portal_quote_tag


router = APIRouter(prefix="/cases/{case_id}/files", tags=["files"])
log = logging.getLogger(__name__)


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_case_file(
    case_id: uuid.UUID,
    upload: UploadFile = FastAPIFile(...),
    folder: str = Form(default=""),
    parent_file_id: uuid.UUID | None = Form(default=None),
    notify_portal_contacts: bool = Form(default=False),
    compose_precedent_id: uuid.UUID | None = Form(default=None),
    compose_case_contact_id: uuid.UUID | None = Form(default=None),
    compose_global_contact_id: uuid.UUID | None = Form(default=None),
    source_imap_mbox: str | None = Form(default=None),
    source_imap_uid: str | None = Form(default=None),
    source_internet_message_id: str | None = Form(default=None),
    outlook_item_id: str | None = Form(default=None),
    outlook_conversation_id: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return upload_case_file_service(
        case_id,
        upload,
        folder=folder,
        parent_file_id=parent_file_id,
        notify_portal_contacts=notify_portal_contacts,
        compose_precedent_id=compose_precedent_id,
        compose_case_contact_id=compose_case_contact_id,
        compose_global_contact_id=compose_global_contact_id,
        source_imap_mbox=source_imap_mbox,
        source_imap_uid=source_imap_uid,
        source_internet_message_id=source_internet_message_id,
        outlook_item_id=outlook_item_id,
        outlook_conversation_id=outlook_conversation_id,
        user=user,
        db=db,
    )


@router.post("/compose-office", status_code=status.HTTP_201_CREATED)
def compose_office_document(
    case_id: uuid.UUID,
    body: ComposeOfficeDocumentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new .docx from a precedent template or from the reserved blank letter / empty document path.

    Letter compose should send ``compose_office_role: \"letter\"`` when ``precedent_id`` is null so the server
    can substitute the ``BLANK_LETTER`` global template.
    """
    return compose_office_document_service(case_id, body, user, db)


@router.post("/compose-quote", status_code=status.HTTP_201_CREATED)
def compose_quote_spreadsheet(
    case_id: uuid.UUID,
    body: ComposeQuoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new quote .docx: quote letterhead template + fee table from the fee scale."""
    return compose_quote_spreadsheet_service(case_id, body, user, db)


@router.get("/compose-handoff-attachments/{file_id}")
def download_compose_handoff_attachment(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    handoff_token: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
):
    """Download a case file listed in a short-lived M365 compose handoff JWT (for OWA drag-and-drop attach)."""
    try:
        payload = decode_compose_handoff_token(handoff_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    if payload.case_id != str(case_id) or str(file_id) not in payload.attachment_file_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token does not allow this file.")
    try:
        owner_id = uuid.UUID(payload.user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from e
    owner = db.get(User, owner_id)
    if not owner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
    require_case_access(case_id, owner, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not path_is_under_files_root(abs_path) or not abs_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    return FileResponse(
        path=str(abs_path),
        media_type=row.mime_type or "application/octet-stream",
        filename=row.original_filename,
        content_disposition_type="attachment",
    )


@router.post("/email-compose-handoff", response_model=CaseEmailComposeHandoffOut)
def create_case_email_compose_handoff(
    case_id: uuid.UUID,
    body: CaseEmailDraftM365In,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseEmailComposeHandoffOut:
    """Build merge + attachments and return a short-lived JWT for Thunderbird ``compose.beginNew``."""
    require_case_access(case_id, user, db)
    to_addr, subject, body_text, attachments = _case_email_compose_bundle(case_id, body, user, db)
    att_ids = [str(fid) for fid in body.attachment_file_ids]
    token = create_compose_handoff_token(
        user_id=str(user.id),
        case_id=str(case_id),
        to=to_addr,
        subject=subject,
        body=body_text,
        attachment_file_ids=att_ids,
    )
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.email_compose_handoff",
        entity_type="case",
        entity_id=str(case_id),
        meta={"attachment_count": len(att_ids), "has_to": bool(to_addr.strip())},
    )
    return CaseEmailComposeHandoffOut(
        handoff_token=token,
        case_id=case_id,
        expires_in_seconds=COMPOSE_HANDOFF_TTL_SECONDS,
    )


@router.post("/email-mailto", response_model=CaseEmailMailtoOut)
def create_case_email_mailto(
    case_id: uuid.UUID,
    body: CaseEmailDraftM365In,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseEmailMailtoOut:
    """Build subject/body/to for a desktop mailto compose (no Microsoft Graph)."""
    require_case_access(case_id, user, db)
    to_addr, subject, body_text, attachments = _case_email_compose_bundle(case_id, body, user, db)
    return CaseEmailMailtoOut(
        to=to_addr,
        subject=subject,
        body=body_text,
        attachment_count=len(attachments),
    )


@router.post("/email-drafts/m365", status_code=status.HTTP_201_CREATED, response_model=CaseEmailDraftM365Out)
def create_case_email_draft_m365(
    case_id: uuid.UUID,
    body: CaseEmailDraftM365In,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseEmailDraftM365Out:
    """Create an Outlook draft in the signed-in user's mailbox via Microsoft Graph (application permissions)."""
    try:
        return _create_case_email_draft_m365_body(case_id, body, user, db)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("M365 email draft failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{type(e).__name__}: {e}",
        ) from e


@router.get("", response_model=list[dict])
def list_case_files(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    from app.models import QuotePortalDelivery
    from sqlalchemy import func

    rows = (
        db.execute(
            select(DbFile, User.display_name, User.email, User.initials)
            .join(User, DbFile.owner_id == User.id)
            .where(DbFile.case_id == case_id, DbFile.oo_compose_pending.is_(False))
            .order_by(DbFile.created_at.desc())
        ).all()
    )
    file_ids = [f.id for (f, _, _, _) in rows]
    delivery_by_file: dict[uuid.UUID, QuotePortalDelivery] = {}
    if file_ids:
        latest_sent = (
            select(
                QuotePortalDelivery.file_id,
                func.max(QuotePortalDelivery.sent_at).label("max_sent"),
            )
            .where(QuotePortalDelivery.file_id.in_(file_ids))
            .group_by(QuotePortalDelivery.file_id)
            .subquery()
        )
        deliveries = (
            db.execute(
                select(QuotePortalDelivery)
                .join(
                    latest_sent,
                    (QuotePortalDelivery.file_id == latest_sent.c.file_id)
                    & (QuotePortalDelivery.sent_at == latest_sent.c.max_sent),
                )
            )
            .scalars()
            .all()
        )
        for d in deliveries:
            delivery_by_file[d.file_id] = d

    from app.docusign_settings import get_docusign_settings
    from app.docusign_signing_service import signing_request_file_list_item, sync_pending_signing_requests
    from app.canary_sign_service import signing_request_file_list_item as canary_signing_file_list_item
    from app.models import (
        CanarySignRequest,
        CanarySignStatus,
        Contact,
        DocusignSigningRequest,
        DocusignSigningStatus,
        PortalFormSubmission,
    )
    from app.portal_service import contact_display_name
    from app.portal_form_service import form_submission_file_list_item

    delivery_contact_ids = {d.contact_id for d in delivery_by_file.values()}
    contacts_by_id: dict[uuid.UUID, Contact] = {}
    if delivery_contact_ids:
        for contact in (
            db.execute(select(Contact).where(Contact.id.in_(delivery_contact_ids))).scalars().all()
        ):
            contacts_by_id[contact.id] = contact

    signing_by_file: dict[uuid.UUID, dict] = {}
    if file_ids:
        if get_docusign_settings(db).enabled:
            sync_pending_signing_requests(db, case_id=case_id, source_file_ids=file_ids)
        signing_rows = (
            db.execute(
                select(DocusignSigningRequest)
                .where(
                    DocusignSigningRequest.source_file_id.in_(file_ids),
                    DocusignSigningRequest.status.in_(
                        (
                            DocusignSigningStatus.pending,
                            DocusignSigningStatus.completed,
                            DocusignSigningStatus.declined,
                            DocusignSigningStatus.voided,
                        )
                    ),
                )
                .order_by(DocusignSigningRequest.created_at.desc())
            )
            .scalars()
            .all()
        )
        for sr in signing_rows:
            if sr.source_file_id and sr.source_file_id not in signing_by_file:
                signing_by_file[sr.source_file_id] = signing_request_file_list_item(sr)

    canary_by_file: dict[uuid.UUID, dict] = {}
    if file_ids:
        canary_rows = (
            db.execute(
                select(CanarySignRequest)
                .where(
                    CanarySignRequest.source_file_id.in_(file_ids),
                    CanarySignRequest.status.in_(
                        (
                            CanarySignStatus.pending,
                            CanarySignStatus.completed,
                            CanarySignStatus.declined,
                            CanarySignStatus.voided,
                            CanarySignStatus.expired,
                        )
                    ),
                )
                .order_by(CanarySignRequest.created_at.desc())
            )
            .scalars()
            .all()
        )
        for sr in canary_rows:
            if sr.source_file_id and sr.source_file_id not in canary_by_file:
                canary_by_file[sr.source_file_id] = canary_signing_file_list_item(sr)

    form_by_file: dict[uuid.UUID, PortalFormSubmission] = {}
    if file_ids:
        form_rows = (
            db.execute(
                select(PortalFormSubmission).where(PortalFormSubmission.snapshot_file_id.in_(file_ids))
            )
            .scalars()
            .all()
        )
        for sub in form_rows:
            if sub.snapshot_file_id and sub.snapshot_file_id not in form_by_file:
                form_by_file[sub.snapshot_file_id] = sub

    out = []
    for (f, owner_display_name, owner_email, owner_initials) in rows:
        item = {
            "id": str(f.id),
            "original_filename": f.original_filename,
            "mime_type": f.mime_type,
            "size_bytes": f.size_bytes,
            "created_at": f.created_at,
            "updated_at": f.updated_at,
            "folder_path": f.folder_path,
            "is_pinned": f.is_pinned,
            "category": f.category,
            "parent_file_id": str(f.parent_file_id) if f.parent_file_id else None,
            "source_imap_mbox": f.source_imap_mbox,
            "source_imap_uid": f.source_imap_uid,
            "source_mail_from_name": f.source_mail_from_name,
            "source_mail_from_email": f.source_mail_from_email,
            "source_mail_is_outbound": f.source_mail_is_outbound,
            "source_mail_date": f.source_mail_date.isoformat() if f.source_mail_date else None,
            "source_internet_message_id": f.source_internet_message_id,
            "source_outlook_item_id": f.source_outlook_item_id,
            "outlook_graph_message_id": f.outlook_graph_message_id,
            "outlook_web_link": f.outlook_web_link,
            "uploaded_via_portal": f.uploaded_via_portal,
            "is_portal_quote": f.is_portal_quote,
            "owner_display_name": "Portal" if f.uploaded_via_portal else owner_display_name,
            "owner_email": None if f.uploaded_via_portal else owner_email,
            "owner_initials": "Portal" if f.uploaded_via_portal else owner_initials,
        }
        delivery = delivery_by_file.get(f.id)
        if delivery is not None:
            contact = contacts_by_id.get(delivery.contact_id)
            item["quote_portal_delivery"] = {
                "id": str(delivery.id),
                "status": delivery.status.value,
                "contact_name": contact_display_name(contact) if contact else "Contact",
                "sent_at": delivery.sent_at.isoformat(),
                "responded_at": delivery.responded_at.isoformat() if delivery.responded_at else None,
                "decline_reason": delivery.decline_reason,
            }
        signing = signing_by_file.get(f.id)
        if signing is not None:
            item["docusign_signing"] = signing
        canary = canary_by_file.get(f.id)
        if canary is not None:
            item["canary_signing"] = canary
        form_sub = form_by_file.get(f.id)
        if form_sub is not None:
            item["portal_form_submission"] = form_submission_file_list_item(db, form_sub)
        out.append(item)
    return out


@router.get("/portal-folder-access", response_model=list[CasePortalFolderAccessGrantOut])
def list_case_portal_folder_access(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CasePortalFolderAccessGrantOut]:
    """Active client-portal grants for this matter (staff UI: shared folder indicators)."""
    require_case_access(case_id, user, db)
    require_case_portal_enabled(db, case_id)
    rows = (
        db.execute(
            select(ContactPortalGrant, GlobalContactRow)
            .join(GlobalContactRow, ContactPortalGrant.contact_id == GlobalContactRow.id)
            .where(ContactPortalGrant.case_id == case_id)
            .order_by(GlobalContactRow.name.asc())
        )
        .all()
    )
    out: list[CasePortalFolderAccessGrantOut] = []
    for grant, contact in rows:
        if not grant_is_client_visible(db, grant):
            continue
        out.append(
            CasePortalFolderAccessGrantOut(
                folder_path=grant.folder_path or "",
                contact_id=contact.id,
                contact_name=(contact.name or "").strip() or "Contact",
            )
        )
    return out



@router.post("/folders", status_code=status.HTTP_201_CREATED)
def create_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_case_folder_service(case_id=case_id, payload=payload, user=user, db=db)


@router.post("/folders/rename", status_code=status.HTTP_200_OK)
def rename_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderRenameUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return rename_case_folder_service(case_id=case_id, payload=payload, user=user, db=db)


@router.post("/folders/delete", status_code=status.HTTP_200_OK)
def delete_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderDeleteUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_case_folder_service(case_id=case_id, payload=payload, user=user, db=db)


@router.post("/folders/move", status_code=status.HTTP_200_OK)
def move_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderMoveUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return move_case_folder_service(case_id=case_id, payload=payload, user=user, db=db)


@router.get("/export-zip")
def download_case_export_zip(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download all matter files plus ``case-details.txt`` (Case details panel) as a zip."""
    return download_case_export_zip_service(case_id=case_id, user=user, db=db)


@router.get("/folders/download-zip")
def download_case_folder_zip(
    case_id: uuid.UUID,
    folder_path: str = Query(..., description="Case folder_path (encoded segments, slash-separated)."),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download all non-folder files under ``folder_path`` as a single .zip (relative paths preserved)."""
    return download_case_folder_zip_service(case_id=case_id, folder_path=folder_path, user=user, db=db)


@router.patch("/{file_id}/pin", status_code=status.HTTP_200_OK)
def set_file_pin(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: FilePinUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return set_file_pin_service(case_id=case_id, file_id=file_id, payload=payload, user=user, db=db)


@router.patch("/{file_id}/portal-quote-tag", status_code=status.HTTP_200_OK)
def set_file_portal_quote_tag(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: PortalQuoteTagUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    row = set_portal_quote_tag(
        db,
        case_id=case_id,
        file_id=file_id,
        is_portal_quote=payload.is_portal_quote,
        actor_user_id=user.id,
    )
    return {"id": str(row.id), "is_portal_quote": row.is_portal_quote}


@router.patch("/{file_id}/rename", status_code=status.HTTP_200_OK)
def rename_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: CaseFileRenameUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return rename_case_file_service(case_id=case_id, file_id=file_id, payload=payload, user=user, db=db)


@router.patch("/{file_id}/comment", status_code=status.HTTP_200_OK)
def update_comment_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: CommentFileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the text content of a comment (.txt) file and auto-rename it from the first line."""
    return update_comment_file_service(case_id=case_id, file_id=file_id, payload=payload, user=user, db=db)


@router.post("/{file_id}/move", status_code=status.HTTP_200_OK)
def move_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: CaseFileMoveUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return move_case_file_service(case_id=case_id, file_id=file_id, payload=payload, user=user, db=db)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_case_file_service(case_id=case_id, file_id=file_id, user=user, db=db)


@router.post("/{file_id}/checkout-edit", response_model=FileDesktopCheckoutOut, status_code=status.HTTP_201_CREATED)
def checkout_desktop_edit(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileDesktopCheckoutOut:
    return checkout_desktop_edit_service(case_id=case_id, file_id=file_id, user=user, db=db)


@router.get("/{file_id}/onlyoffice-config", response_model=OnlyofficeEditorConfigOut)
def get_onlyoffice_editor_config(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnlyofficeEditorConfigOut:
    return get_onlyoffice_editor_config_service(
        case_id=case_id, file_id=file_id, request=request, response=response, user=user, db=db
    )


@router.post("/{file_id}/oo-force-save")
async def oo_force_save(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    doc_key: str = Query(..., description="OO DS document key from the editor config"),
    phase: OoForceSavePhase = Query(
        "command",
        description=(
            "``arm``: mark pending save and return base_version; "
            "``wait``: block until callback (prefer client poll via GET oo-save-status); "
            "``command``: issue CommandService forcesave only; "
            "``command_wait``: CommandService + block until callback"
        ),
    ),
    base_version: int | None = Query(
        None,
        description="Version from ``phase=arm``; required for ``phase=wait``",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist in-browser ONLYOFFICE edits to Canary storage.

    Preferred flow (matches toolbar Save): arm → host ``serviceCommand('save')`` → wait.
    """
    return await oo_force_save_service(
        case_id=case_id,
        file_id=file_id,
        doc_key=doc_key,
        phase=phase,
        base_version=base_version,
        user=user,
        db=db,
    )


@router.post("/{file_id}/oo-export-pdf", response_model=OoExportPdfOut)
async def oo_export_pdf(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    body: OoExportPdfIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OoExportPdfOut:
    """Save ONLYOFFICE ``downloadAs('pdf')`` as a new case file (does not replace the source document)."""
    return await oo_export_pdf_service(case_id=case_id, file_id=file_id, body=body, user=user, db=db)


@router.post("/{file_id}/oo-persist-download", status_code=status.HTTP_204_NO_CONTENT)
async def oo_persist_download(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    body: OoPersistDownloadIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Persist ONLYOFFICE ``downloadAs`` export bytes to case file storage (PDF and Office)."""
    return await oo_persist_download_service(case_id=case_id, file_id=file_id, body=body, user=user, db=db)


@router.get("/{file_id}/oo-save-status")
def oo_save_status(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    base_version: int = Query(..., description="Version from ``phase=arm`` before triggering ONLYOFFICE save"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int | bool]:
    """Poll whether ONLYOFFICE callback has persisted edits (version bumped past ``base_version``)."""
    return oo_save_status_service(
        case_id=case_id, file_id=file_id, base_version=base_version, user=user, db=db
    )


@router.post("/{file_id}/publish-compose", status_code=status.HTTP_204_NO_CONTENT)
def publish_compose_office_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: PublishComposeIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Show a compose-office document in the case file list (after OnlyOffice Save Changes).

    Idempotent: if the file is not a pending compose, succeeds with no change.
    """
    return publish_compose_office_file_service(
        case_id=case_id, file_id=file_id, payload=payload, user=user, db=db
    )


@router.post("/{file_id}/discard-edit", status_code=status.HTTP_204_NO_CONTENT)
def discard_onlyoffice_edit(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Discard in-browser edits: restore pre-edit backup and release the edit session."""
    return discard_onlyoffice_edit_service(case_id=case_id, file_id=file_id, user=user, db=db)


@router.get("/{file_id}/edit-session", response_model=FileEditSessionStatusOut)
def get_desktop_edit_session(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileEditSessionStatusOut:
    return get_desktop_edit_session_service(case_id=case_id, file_id=file_id, user=user, db=db)


@router.post("/{file_id}/release-edit", status_code=status.HTTP_204_NO_CONTENT)
def release_desktop_edit(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    return release_desktop_edit_service(case_id=case_id, file_id=file_id, user=user, db=db)


@router.post("/{file_id}/eml-open-token")
def issue_eml_open_token(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not _row_is_eml_like(row):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only e-mail messages (.eml / RFC822) can be opened with your mail app.",
        )
    tok = create_eml_open_token(user_id=str(user.id), case_id=str(case_id), file_id=str(file_id))
    return {"token": tok}


@router.get("/{file_id}/eml-open")
def download_eml_for_mail_client(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    token: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """Serve the .eml with ``Content-Disposition: attachment`` so the browser hands off to the OS mail app (no blob: URL)."""
    try:
        payload = decode_eml_open_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired link")
    try:
        if uuid.UUID(payload.case_id) != case_id or uuid.UUID(payload.file_id) != file_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid link")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid link")

    user = db.get(User, uuid.UUID(payload.user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid link")
    require_case_access(case_id, user, db)

    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not _row_is_eml_like(row):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not path_is_under_files_root(abs_path) or not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")

    fname = Path(row.original_filename).name
    if not fname.lower().endswith(".eml"):
        fname = f"{Path(fname).stem or 'message'}.eml"

    return FileResponse(
        path=str(abs_path),
        media_type="message/rfc822",
        filename=fname,
        content_disposition_type="attachment",
    )


@router.get("/{file_id}/outlook-open-hints", response_model=OutlookOpenHintsOut)
def get_case_file_outlook_open_hints(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    owa_base: str | None = Query(default=None, max_length=2000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookOpenHintsOut:
    """Return stored Graph / OWA pointers; may backfill ``outlook_web_link`` when Graph is configured."""
    from app.graph_outlook_categories import resolve_outlook_owa_link_via_conversation
    from app.owa_urls import effective_owa_base_for_open, is_canary_synthetic_message_id, resolve_owa_read_url_for_file

    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    try:
        repair_outlook_web_link_on_file(db, row)
    except Exception:
        log.warning("get_case_file_outlook_open_hints: repair web link failed", exc_info=True)
    row = db.get(DbFile, file_id)
    if row and row.case_id == case_id:
        owner = db.get(User, row.owner_id)
        conv = (row.source_outlook_conversation_id or "").strip()
        if (
            owner
            and (owner.email or "").strip()
            and conv
            and not (row.outlook_graph_message_id or row.source_outlook_item_id or "").strip()
            and is_canary_synthetic_message_id(row.source_internet_message_id)
        ):
            try:
                wl, gid = resolve_outlook_owa_link_via_conversation(
                    owner.email.strip(),
                    conv,
                    db=db,
                )
            except Exception:
                log.warning("get_case_file_outlook_open_hints: conversation Graph lookup failed", exc_info=True)
                wl, gid = None, None
            if wl or gid:
                if wl:
                    row.outlook_web_link = wl
                if gid:
                    row.source_outlook_item_id = gid
                    storable = _outlook_graph_message_id_storable(gid)
                    if storable:
                        row.outlook_graph_message_id = storable
                row.updated_at = datetime.now(timezone.utc)
                db.add(row)
                db.commit()
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    owner = db.get(User, row.owner_id)
    mid = (row.source_outlook_item_id or row.outlook_graph_message_id or "").strip()
    if owner and (owner.email or "").strip() and mid and graph_mail_configured(db):
        from app.graph_outlook_categories import resolve_outlook_owa_link_via_graph

        try:
            wl, resolved_gid = resolve_outlook_owa_link_via_graph(
                owner.email.strip(),
                mid,
                row.source_internet_message_id,
                db=db,
            )
        except Exception:
            log.warning("get_case_file_outlook_open_hints: refresh webLink failed", exc_info=True)
            wl, resolved_gid = None, None
        if wl or resolved_gid:
            if wl:
                row.outlook_web_link = wl
            if resolved_gid:
                row.source_outlook_item_id = resolved_gid
                storable = _outlook_graph_message_id_storable(resolved_gid)
                if storable:
                    row.outlook_graph_message_id = storable
            row.updated_at = datetime.now(timezone.utc)
            db.add(row)
            db.commit()
    gid = row.source_outlook_item_id or row.outlook_graph_message_id
    base = effective_owa_base_for_open(owa_base, db)
    read_url = resolve_owa_read_url_for_file(
        outlook_graph_message_id=row.outlook_graph_message_id,
        source_outlook_item_id=row.source_outlook_item_id,
        outlook_web_link=row.outlook_web_link,
        source_internet_message_id=row.source_internet_message_id,
        owa_base=base,
    )
    return OutlookOpenHintsOut(
        outlook_graph_message_id=gid,
        outlook_web_link=row.outlook_web_link,
        owa_read_url=read_url,
        open_in_owa_supported=read_url is not None,
    )


@router.get("/{file_id}")
def download_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # storage_path is relative to FILES_ROOT
    ensure_files_root()
    from app.file_storage import FILES_ROOT

    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not path_is_under_files_root(abs_path) or not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")

    # Safe MIME types may render inline; others force download.
    return FileResponse(
        path=str(abs_path),
        media_type=row.mime_type,
        filename=row.original_filename,
        content_disposition_type=content_disposition_for_mime(row.mime_type, download=False),
    )

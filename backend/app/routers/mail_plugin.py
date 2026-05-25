"""Mail-client helpers (Thunderbird add-on, etc.). Outlook add-in routes remain under ``/outlook-plugin``."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.models import User
from app.mail_compose_bundle import build_mail_compose_bundle, encode_compose_attachments
from app.routers import outlook_plugin as outlook_plugin_router
from app.schemas import (
    CaseEmailDraftM365In,
    MailPluginComposeHandoffOut,
    MailPluginMessageContextOut,
    OutlookPluginLinkedCaseResolveIn,
    OutlookPluginLinkedCaseResolveOut,
    OutlookPluginPendingSendOut,
    OutlookPluginPendingSendPutIn,
)
from app.security import ComposeHandoffTokenPayload, decode_compose_handoff_token

router = APIRouter(prefix="/mail-plugin", tags=["mail-plugin"])
log = logging.getLogger(__name__)


@router.post("/linked-case", response_model=OutlookPluginLinkedCaseResolveOut)
def mail_plugin_linked_case(
    payload: OutlookPluginLinkedCaseResolveIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginLinkedCaseResolveOut:
    return outlook_plugin_router.resolve_linked_case_for_outlook_message(payload, user, db)


@router.post("/message-context", response_model=MailPluginMessageContextOut)
def mail_plugin_message_context(
    payload: OutlookPluginLinkedCaseResolveIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailPluginMessageContextOut:
    """Matter + filed .eml row for reply prefill (Message-ID / IMAP / Outlook ids)."""
    return outlook_plugin_router.resolve_message_filing_context(payload, user, db)


@router.get("/pending-send", response_model=OutlookPluginPendingSendOut)
def mail_plugin_get_pending_send(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginPendingSendOut:
    return outlook_plugin_router.outlook_plugin_get_pending_send(user, db)


@router.put("/pending-send", response_model=OutlookPluginPendingSendOut)
def mail_plugin_put_pending_send(
    payload: OutlookPluginPendingSendPutIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginPendingSendOut:
    return outlook_plugin_router.outlook_plugin_put_pending_send(payload, user, db)


@router.delete("/pending-send", status_code=status.HTTP_204_NO_CONTENT)
def mail_plugin_delete_pending_send(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    return outlook_plugin_router.outlook_plugin_delete_pending_send(user, db)


@router.post("/cases/{case_id}/compose-bundle", response_model=MailPluginComposeHandoffOut)
def mail_plugin_compose_bundle(
    case_id: UUID,
    body: CaseEmailDraftM365In,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailPluginComposeHandoffOut:
    """Thunderbird compose panel: merged body, headers, and attachment bytes (Bearer auth)."""
    return build_mail_compose_bundle(db, case_id, body, user)


@router.get("/compose-handoff/{handoff_token}", response_model=MailPluginComposeHandoffOut)
def mail_plugin_get_compose_handoff(
    handoff_token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MailPluginComposeHandoffOut:
    """Thunderbird add-on: fetch merged body, headers, and attachment bytes for ``compose.beginNew``."""
    try:
        payload: ComposeHandoffTokenPayload = decode_compose_handoff_token(handoff_token.strip())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if str(user.id) != payload.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Handoff token does not match this user.")
    try:
        case_id = UUID(payload.case_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid case id in handoff.") from e
    require_case_access(case_id, user, db)
    att_uuids: list[UUID] = []
    for fid_s in payload.attachment_file_ids:
        try:
            att_uuids.append(UUID(fid_s))
        except ValueError:
            continue
    attachments = encode_compose_attachments(db, case_id, user, att_uuids)
    return MailPluginComposeHandoffOut(
        case_id=case_id,
        to=payload.to,
        subject=payload.subject,
        body=payload.body,
        attachments=attachments,
    )

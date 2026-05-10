"""API used by the Outlook add-in task pane (cross-case helpers)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.graph_mail import graph_mail_configured
from app.graph_outlook_categories import ensure_master_category_for_mailbox, merge_canary_category_on_message
from app.models import Case as CaseRow
from app.models import File as DbFile
from app.models import User
from app.schemas import (
    OutlookPluginEnsureMasterCategoryIn,
    OutlookPluginEnsureMasterCategoryOut,
    OutlookPluginGraphTagCategoryIn,
    OutlookPluginGraphTagCategoryOut,
    OutlookPluginLinkedCaseOut,
    OutlookPluginLinkedCaseResolveIn,
    OutlookPluginLinkedCaseResolveOut,
    OutlookPluginPendingSendOut,
    OutlookPluginPendingSendPutIn,
)

router = APIRouter(prefix="/outlook-plugin", tags=["outlook-plugin"])
log = logging.getLogger(__name__)

_PENDING_TTL_MIN = 60
_PENDING_TTL_MAX = 86400 * 7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clear_expired_pending(db: Session, user_row: User) -> None:
    exp = user_row.outlook_pending_send_expires_at
    if exp is not None and exp < _utcnow():
        user_row.outlook_pending_send_case_id = None
        user_row.outlook_pending_send_source_file_id = None
        user_row.outlook_pending_send_expires_at = None


def _internet_message_id_variants(raw: str | None) -> list[str]:
    t = (raw or "").strip()
    if not t:
        return []
    out: set[str] = {t}
    if t.startswith("<") and t.endswith(">"):
        inner = t[1:-1].strip()
        if inner:
            out.add(inner)
    elif "@" in t:
        out.add(f"<{t}>")
    return list(out)


@router.post("/linked-case", response_model=OutlookPluginLinkedCaseResolveOut)
def resolve_linked_case_for_outlook_message(
    payload: OutlookPluginLinkedCaseResolveIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginLinkedCaseResolveOut:
    """Return the matter a message is already filed to, if any, by Outlook item id and/or RFC5322 Message-ID."""
    oid = (payload.outlook_item_id or "").strip() or None
    variants = _internet_message_id_variants(payload.internet_message_id)
    conv = (payload.conversation_id or "").strip() or None
    if not oid and not variants and not conv:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide outlook_item_id, internet_message_id, and/or conversation_id.",
        )

    top_ors = []
    if oid:
        top_ors.append(or_(DbFile.source_outlook_item_id == oid, DbFile.outlook_graph_message_id == oid))
    if variants:
        top_ors.append(DbFile.source_internet_message_id.in_(variants))
    if conv:
        top_ors.append(DbFile.source_outlook_conversation_id == conv)
    if not top_ors:
        return OutlookPluginLinkedCaseResolveOut(linked_case=None)

    stmt = (
        select(DbFile, CaseRow)
        .join(CaseRow, DbFile.case_id == CaseRow.id)
        .where(or_(*top_ors))
        .where(DbFile.oo_compose_pending.is_(False))
        .order_by(DbFile.created_at.desc())
        .limit(40)
    )
    rows = db.execute(stmt).all()
    for _frow, case in rows:
        try:
            require_case_access(case.id, user, db)
        except HTTPException:
            continue
        return OutlookPluginLinkedCaseResolveOut(
            linked_case=OutlookPluginLinkedCaseOut(
                id=case.id,
                case_number=case.case_number,
                client_name=case.client_name,
                matter_description=case.title,
            )
        )
    return OutlookPluginLinkedCaseResolveOut(linked_case=None)


@router.get("/pending-send", response_model=OutlookPluginPendingSendOut)
def outlook_plugin_get_pending_send(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginPendingSendOut:
    row = db.get(User, user.id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _clear_expired_pending(db, row)
    db.commit()
    db.refresh(row)
    cid = row.outlook_pending_send_case_id
    if not cid or not row.outlook_pending_send_expires_at:
        return OutlookPluginPendingSendOut(active=False)
    try:
        require_case_access(cid, user, db)
    except HTTPException:
        row.outlook_pending_send_case_id = None
        row.outlook_pending_send_source_file_id = None
        row.outlook_pending_send_expires_at = None
        db.commit()
        return OutlookPluginPendingSendOut(active=False)
    return OutlookPluginPendingSendOut(
        active=True,
        case_id=cid,
        source_file_id=row.outlook_pending_send_source_file_id,
        expires_at=row.outlook_pending_send_expires_at,
    )


@router.put("/pending-send", response_model=OutlookPluginPendingSendOut)
def outlook_plugin_put_pending_send(
    payload: OutlookPluginPendingSendPutIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginPendingSendOut:
    require_case_access(payload.case_id, user, db)
    ttl = payload.ttl_seconds if payload.ttl_seconds is not None else 86400
    ttl = max(_PENDING_TTL_MIN, min(_PENDING_TTL_MAX, int(ttl)))

    src_fid = payload.source_file_id
    if src_fid is not None:
        frow = db.get(DbFile, src_fid)
        if not frow or frow.case_id != payload.case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_file_id is invalid for this matter.",
            )

    row = db.get(User, user.id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    row.outlook_pending_send_case_id = payload.case_id
    row.outlook_pending_send_source_file_id = src_fid
    row.outlook_pending_send_expires_at = _utcnow() + timedelta(seconds=ttl)
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return OutlookPluginPendingSendOut(
        active=True,
        case_id=row.outlook_pending_send_case_id,
        source_file_id=row.outlook_pending_send_source_file_id,
        expires_at=row.outlook_pending_send_expires_at,
    )


@router.delete("/pending-send", status_code=status.HTTP_204_NO_CONTENT)
def outlook_plugin_delete_pending_send(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(User, user.id)
    if not row:
        return
    row.outlook_pending_send_case_id = None
    row.outlook_pending_send_source_file_id = None
    row.outlook_pending_send_expires_at = None
    row.updated_at = _utcnow()
    db.commit()


@router.post("/ensure-master-category", response_model=OutlookPluginEnsureMasterCategoryOut)
def outlook_plugin_ensure_master_category(
    payload: OutlookPluginEnsureMasterCategoryIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginEnsureMasterCategoryOut:
    """
    Idempotently create the configured Outlook **master** category (``CANARY_OUTLOOK_CATEGORY_NAME``)
    in the user’s Exchange mailbox via Microsoft Graph (application permissions).

    The add-in still applies the category to the message with Office.js; this only seeds the
    mailbox master list so ``categories.addAsync`` succeeds without manual Outlook setup.

    Requires Entra app permission **MailboxSettings.ReadWrite** (application) + admin consent,
    plus existing ``CANARY_MS_GRAPH_*`` variables.
    """
    mailbox = (payload.mailbox or "").strip()
    if not mailbox:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mailbox is required.")

    if (user.email or "").strip().lower() != mailbox.lower():
        return OutlookPluginEnsureMasterCategoryOut(
            ok=False,
            status="skipped_mailbox_mismatch",
            detail="Mailbox must match your Canary sign-in email for Graph provisioning.",
        )

    if not graph_mail_configured(db):
        return OutlookPluginEnsureMasterCategoryOut(
            ok=False,
            status="skipped_graph_not_configured",
            detail="Server Graph credentials are not configured.",
        )

    try:
        result = ensure_master_category_for_mailbox(mailbox, db)
        st = str(result.get("status") or "")
        if st in ("created", "already_present"):
            return OutlookPluginEnsureMasterCategoryOut(ok=True, status=st, detail=None)
        return OutlookPluginEnsureMasterCategoryOut(ok=False, status=st or "unknown", detail=None)
    except RuntimeError as e:
        log.warning("ensure_master_category_for_mailbox failed: %s", e)
        return OutlookPluginEnsureMasterCategoryOut(
            ok=False,
            status="graph_error",
            detail=str(e)[:800],
        )


@router.post("/graph-tag-category", response_model=OutlookPluginGraphTagCategoryOut)
def outlook_plugin_graph_tag_category(
    payload: OutlookPluginGraphTagCategoryIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OutlookPluginGraphTagCategoryOut:
    """
    Apply the configured category name to **this message** via Graph ``PATCH …/messages/{id}``
    (fallback when Office.js ``categories.addAsync`` fails).

    Entra app needs **Mail.ReadWrite** (application) + admin consent, plus ``CANARY_MS_GRAPH_*``.
    """
    mailbox = (payload.mailbox or "").strip()
    rest_item_id = (payload.rest_item_id or "").strip()
    if not mailbox or not rest_item_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mailbox and rest_item_id are required.",
        )
    if (user.email or "").strip().lower() != mailbox.lower():
        return OutlookPluginGraphTagCategoryOut(
            ok=False,
            status="skipped_mailbox_mismatch",
            detail="Mailbox must match your Canary sign-in email.",
        )
    if not graph_mail_configured(db):
        return OutlookPluginGraphTagCategoryOut(
            ok=False,
            status="skipped_graph_not_configured",
            detail="Server Graph credentials are not configured.",
        )
    try:
        result = merge_canary_category_on_message(
            mailbox,
            rest_item_id,
            (payload.internet_message_id or "").strip() or None,
            db=db,
        )
        st = str(result.get("status") or "")
        if st in ("tagged", "already_tagged"):
            return OutlookPluginGraphTagCategoryOut(ok=True, status=st, detail=None)
        return OutlookPluginGraphTagCategoryOut(ok=False, status=st or "unknown", detail=None)
    except RuntimeError as e:
        log.warning("merge_canary_category_on_message failed: %s", e)
        return OutlookPluginGraphTagCategoryOut(
            ok=False,
            status="graph_error",
            detail=str(e)[:800],
        )

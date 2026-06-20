"""Ledger endpoints: GET /cases/{case_id}/ledger and POST /cases/{case_id}/ledger/post."""
from __future__ import annotations

import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.ledger_audit import log_ledger_approve, log_ledger_edit, log_ledger_post, log_ledger_reject
from app.ledger_export import build_case_ledger_workbook
from app.ledger_service import (
    approve_ledger_pair,
    get_ledger,
    post_transaction,
    reject_ledger_pair_unapproved,
    update_ledger_pair_unapproved,
)
from app.models import Case, User
from app.schemas import LedgerOut, LedgerPairUpdate, LedgerPostCreate

router = APIRouter(prefix="/cases", tags=["ledger"])


@router.get("/{case_id}/ledger", response_model=LedgerOut)
def read_ledger(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LedgerOut:
    require_case_access(case_id, user, db)
    return get_ledger(case_id, db)


@router.get("/{case_id}/ledger/export")
def export_ledger(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    require_case_access(case_id, user, db)
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    ledger = get_ledger(case_id, db)
    wb = build_case_ledger_workbook(case, ledger)
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in case.case_number).strip("-") or "matter"
    filename = f"canary-ledger-{safe_ref}.xlsx"
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{case_id}/ledger/post", status_code=status.HTTP_204_NO_CONTENT)
def create_posting(
    case_id: uuid.UUID,
    payload: LedgerPostCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    result = post_transaction(case_id, payload, user, db)
    db.commit()
    log_ledger_post(
        db,
        actor_user_id=user.id,
        case_id=case_id,
        pair_id=result.pair_id,
        payload=payload,
        is_approved=result.is_approved,
    )


@router.post("/{case_id}/ledger/approve/{pair_id}", status_code=status.HTTP_204_NO_CONTENT)
def approve_posting(
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    approve_ledger_pair(case_id, pair_id, user, db)
    db.commit()
    log_ledger_approve(db, actor_user_id=user.id, case_id=case_id, pair_id=pair_id)


@router.patch("/{case_id}/ledger/pairs/{pair_id}", status_code=status.HTTP_204_NO_CONTENT)
def edit_posting(
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    payload: LedgerPairUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    update_ledger_pair_unapproved(case_id, pair_id, payload, user, db)
    db.commit()
    log_ledger_edit(db, actor_user_id=user.id, case_id=case_id, pair_id=pair_id, payload=payload)


@router.delete("/{case_id}/ledger/pairs/{pair_id}", status_code=status.HTTP_204_NO_CONTENT)
def reject_posting(
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    reject_ledger_pair_unapproved(case_id, pair_id, user, db)
    db.commit()
    log_ledger_reject(db, actor_user_id=user.id, case_id=case_id, pair_id=pair_id)

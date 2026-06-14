"""Case time entry CRUD (Phase 1 — log unbilled time in 6-minute units)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.case_time_service import (
    assert_entry_editable,
    resolve_non_billable,
    resolve_time_entry_user_id,
    time_entry_out,
    user_may_modify_time_entry,
    validate_duration_minutes,
)
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.models import CaseTimeEntry, CaseTimeEntryStatus, User
from app.schemas import CaseTimeEntryCreate, CaseTimeEntryOut, CaseTimeEntryUpdate

router = APIRouter(prefix="/cases/{case_id}/time", tags=["case-time"])


@router.get("", response_model=list[CaseTimeEntryOut])
def list_time_entries(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CaseTimeEntryOut]:
    require_case_access(case_id, user, db)
    rows = (
        db.execute(
            select(CaseTimeEntry)
            .where(CaseTimeEntry.case_id == case_id)
            .order_by(CaseTimeEntry.work_date.desc(), CaseTimeEntry.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [CaseTimeEntryOut.model_validate(time_entry_out(r, db)) for r in rows]


@router.post("", response_model=CaseTimeEntryOut, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    case_id: uuid.UUID,
    payload: CaseTimeEntryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseTimeEntryOut:
    require_case_access(case_id, user, db)
    validate_duration_minutes(payload.duration_minutes)
    target_user_id = resolve_time_entry_user_id(
        payload_user_id=payload.user_id,
        actor=user,
        db=db,
    )
    target_user = db.get(User, target_user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="User not found.")
    non_billable = resolve_non_billable(non_billable=payload.non_billable, target_user=target_user)
    now = datetime.utcnow()
    row = CaseTimeEntry(
        id=uuid.uuid4(),
        case_id=case_id,
        user_id=target_user_id,
        created_by_user_id=user.id,
        work_date=payload.work_date,
        duration_minutes=payload.duration_minutes,
        description=payload.description.strip(),
        status=CaseTimeEntryStatus.unbilled,
        non_billable=non_billable,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.time.create",
        entity_type="case_time_entry",
        entity_id=str(row.id),
        meta={
            "case_id": str(case_id),
            "user_id": str(target_user_id),
            "work_date": payload.work_date.isoformat(),
            "duration_minutes": payload.duration_minutes,
        },
    )
    return CaseTimeEntryOut.model_validate(time_entry_out(row, db))


@router.patch("/{entry_id}", response_model=CaseTimeEntryOut)
def update_time_entry(
    case_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: CaseTimeEntryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseTimeEntryOut:
    require_case_access(case_id, user, db)
    row = db.get(CaseTimeEntry, entry_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")
    if not user_may_modify_time_entry(row, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this entry")
    assert_entry_editable(row)

    data = payload.model_dump(exclude_unset=True)
    if "duration_minutes" in data:
        validate_duration_minutes(data["duration_minutes"])
    if "description" in data and data["description"] is not None:
        data["description"] = data["description"].strip()
    if "user_id" in data:
        data["user_id"] = resolve_time_entry_user_id(
            payload_user_id=data["user_id"],
            actor=user,
            db=db,
        )
    target_user_id = data.get("user_id", row.user_id)
    target_user = db.get(User, target_user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="User not found.")
    non_billable = data.get("non_billable", row.non_billable)
    data["non_billable"] = resolve_non_billable(non_billable=non_billable, target_user=target_user)
    for key, val in data.items():
        setattr(row, key, val)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.time.update",
        entity_type="case_time_entry",
        entity_id=str(row.id),
        meta={"case_id": str(case_id), **{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in data.items()}},
    )
    return CaseTimeEntryOut.model_validate(time_entry_out(row, db))


@router.post("/{entry_id}/write-off", response_model=CaseTimeEntryOut)
def write_off_time_entry(
    case_id: uuid.UUID,
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseTimeEntryOut:
    require_case_access(case_id, user, db)
    row = db.get(CaseTimeEntry, entry_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")
    if not user_may_modify_time_entry(row, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to write off this entry")
    assert_entry_editable(row)
    row.status = CaseTimeEntryStatus.written_off
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.time.write_off",
        entity_type="case_time_entry",
        entity_id=str(row.id),
        meta={"case_id": str(case_id)},
    )
    return CaseTimeEntryOut.model_validate(time_entry_out(row, db))


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_entry(
    case_id: uuid.UUID,
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    row = db.get(CaseTimeEntry, entry_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")
    if not user_may_modify_time_entry(row, user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this entry")
    assert_entry_editable(row)
    db.delete(row)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="case.time.delete",
        entity_type="case_time_entry",
        entity_id=str(entry_id),
        meta={"case_id": str(case_id)},
    )
    return None

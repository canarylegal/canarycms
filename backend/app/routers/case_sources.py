"""Referral source labels for cases (Quotes → Sources)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import CaseSource, User
from app.schemas import CaseSourceAdminUpdate, CaseSourceCreate, CaseSourceOut

router = APIRouter(prefix="/case-sources", tags=["case-sources"])


@router.get("", response_model=list[CaseSourceOut])
def list_case_sources(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CaseSourceOut]:
    rows = (
        db.execute(select(CaseSource).order_by(CaseSource.sort_order, CaseSource.name))
        .scalars()
        .all()
    )
    return [CaseSourceOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("", response_model=CaseSourceOut, status_code=status.HTTP_201_CREATED)
def create_case_source(
    payload: CaseSourceCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseSourceOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required.")
    exists = db.execute(select(CaseSource).where(func.lower(CaseSource.name) == name.lower())).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That source name already exists.")
    max_order = db.scalar(select(func.coalesce(func.max(CaseSource.sort_order), -1))) or -1
    now = datetime.now(timezone.utc)
    row = CaseSource(
        id=uuid.uuid4(),
        name=name,
        sort_order=int(max_order) + 1,
        is_system=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return CaseSourceOut.model_validate(row, from_attributes=True)


@router.patch("/{source_id}", response_model=CaseSourceOut)
def admin_update_case_source(
    source_id: uuid.UUID,
    payload: CaseSourceAdminUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CaseSourceOut:
    row = db.get(CaseSource, source_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    if row.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Built-in sources cannot be edited.")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        new_name = data["name"].strip()
        if not new_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required.")
        clash = db.execute(
            select(CaseSource).where(func.lower(CaseSource.name) == new_name.lower(), CaseSource.id != source_id)
        ).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That source name already exists.")
        row.name = new_name
    if "sort_order" in data and data["sort_order"] is not None:
        row.sort_order = data["sort_order"]
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return CaseSourceOut.model_validate(row, from_attributes=True)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_case_source(
    source_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(CaseSource, source_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")
    if row.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Built-in sources cannot be deleted.")
    db.delete(row)
    db.commit()

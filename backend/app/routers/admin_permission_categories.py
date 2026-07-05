"""Admin CRUD for user permission categories."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth_principal import AuthPrincipal
from app.db import get_db
from app.deps import require_recovery_operator
from app.permission_category_bootstrap import is_builtin_category_id
from app.models import User, UserPermissionCategory
from app.schemas import UserPermissionCategoryCreate, UserPermissionCategoryOut, UserPermissionCategoryPatch

router = APIRouter(prefix="/admin/permission-categories", tags=["admin-permission-categories"])


def _category_out(row: UserPermissionCategory) -> UserPermissionCategoryOut:
    return UserPermissionCategoryOut(
        id=row.id,
        name=row.name,
        perm_fee_earner=row.perm_fee_earner,
        perm_post_client=row.perm_post_client,
        perm_post_office=row.perm_post_office,
        perm_post_anticipated=row.perm_post_anticipated,
        perm_approve_payments=row.perm_approve_payments,
        perm_approve_invoices=row.perm_approve_invoices,
        perm_admin=row.perm_admin,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_builtin_template=is_builtin_category_id(row.id),
    )


@router.get("", response_model=list[UserPermissionCategoryOut])
def list_categories(
    _operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> list[UserPermissionCategoryOut]:
    rows = (
        db.execute(select(UserPermissionCategory).order_by(UserPermissionCategory.name.asc()))
        .scalars()
        .all()
    )
    rows.sort(key=lambda r: (not is_builtin_category_id(r.id), r.name.lower()))
    return [_category_out(r) for r in rows]


@router.post("", response_model=UserPermissionCategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: UserPermissionCategoryCreate,
    _operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> UserPermissionCategoryOut:
    now = datetime.utcnow()
    row = UserPermissionCategory(
        id=uuid.uuid4(),
        name=payload.name.strip(),
        perm_fee_earner=payload.perm_fee_earner,
        perm_post_client=payload.perm_post_client,
        perm_post_office=payload.perm_post_office,
        perm_post_anticipated=payload.perm_post_anticipated,
        perm_approve_payments=payload.perm_approve_payments,
        perm_approve_invoices=payload.perm_approve_invoices,
        perm_admin=payload.perm_admin,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category name may already exist.")
    db.refresh(row)
    return _category_out(row)


@router.patch("/{category_id}", response_model=UserPermissionCategoryOut)
def patch_category(
    category_id: uuid.UUID,
    payload: UserPermissionCategoryPatch,
    _operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> UserPermissionCategoryOut:
    row = db.get(UserPermissionCategory, category_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    for k in (
        "perm_fee_earner",
        "perm_post_client",
        "perm_post_office",
        "perm_post_anticipated",
        "perm_approve_payments",
        "perm_approve_invoices",
        "perm_admin",
    ):
        if k in data and data[k] is not None:
            setattr(row, k, data[k])
    row.updated_at = datetime.utcnow()
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update failed.")
    db.refresh(row)
    return _category_out(row)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: uuid.UUID,
    _operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(UserPermissionCategory, category_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    n = db.scalar(select(func.count()).where(User.permission_category_id == category_id)) or 0
    if int(n) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a category that is still assigned to users.",
        )
    db.delete(row)
    db.commit()
    return None

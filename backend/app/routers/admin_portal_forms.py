"""Admin: portal form template precedents."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import MatterHeadType, MatterSubType, PortalFormTemplate, User
from app.portal_form_service import create_template, delete_template, template_out, update_template
from app.schemas import PortalFormTemplateCreate, PortalFormTemplateDetailOut, PortalFormTemplateOut, PortalFormTemplateUpdate

router = APIRouter(prefix="/admin/portal-forms", tags=["admin-portal-forms"])


def _list_order():
    scope_rank = case(
        (
            and_(PortalFormTemplate.matter_head_type_id.is_(None), PortalFormTemplate.matter_sub_type_id.is_(None)),
            0,
        ),
        (PortalFormTemplate.matter_sub_type_id.is_(None), 1),
        else_=2,
    )
    return (
        scope_rank,
        func.lower(func.coalesce(MatterHeadType.name, "")),
        func.lower(func.coalesce(MatterSubType.name, "")),
        func.lower(PortalFormTemplate.name),
    )


@router.get("", response_model=list[PortalFormTemplateOut])
def list_templates(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[PortalFormTemplateOut]:
    rows = (
        db.execute(
            select(PortalFormTemplate)
            .outerjoin(MatterHeadType, PortalFormTemplate.matter_head_type_id == MatterHeadType.id)
            .outerjoin(MatterSubType, PortalFormTemplate.matter_sub_type_id == MatterSubType.id)
            .order_by(*_list_order())
        )
        .scalars()
        .all()
    )
    return [PortalFormTemplateOut.model_validate(template_out(db, t)) for t in rows]


@router.get("/{template_id}", response_model=PortalFormTemplateDetailOut)
def get_template(
    template_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortalFormTemplateDetailOut:
    row = db.get(PortalFormTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return PortalFormTemplateDetailOut.model_validate(template_out(db, row, include_fields=True))


@router.post("", response_model=PortalFormTemplateDetailOut, status_code=status.HTTP_201_CREATED)
def post_template(
    payload: PortalFormTemplateCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortalFormTemplateDetailOut:
    row = create_template(db, payload=payload.model_dump(), owner=admin)
    db.commit()
    db.refresh(row)
    return PortalFormTemplateDetailOut.model_validate(template_out(db, row, include_fields=True))


@router.put("/{template_id}", response_model=PortalFormTemplateDetailOut)
def put_template(
    template_id: uuid.UUID,
    payload: PortalFormTemplateUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortalFormTemplateDetailOut:
    row = db.get(PortalFormTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    update_template(db, template=row, payload=payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return PortalFormTemplateDetailOut.model_validate(template_out(db, row, include_fields=True))


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_template(
    template_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(PortalFormTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    delete_template(db, row)
    db.commit()

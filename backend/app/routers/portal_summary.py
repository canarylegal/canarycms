"""Staff Portal summary desk API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.portal_summary_service import list_portal_summary, portal_summary_options
from app.schemas.portal_summary import (
    PortalSummaryKind,
    PortalSummaryOptionsOut,
    PortalSummaryOut,
    PortalSummaryRowOut,
)

router = APIRouter(prefix="/portal-summary", tags=["portal-summary"])


@router.get("/options", response_model=PortalSummaryOptionsOut)
def get_portal_summary_options(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortalSummaryOptionsOut:
    return portal_summary_options(db)


@router.get("", response_model=PortalSummaryOut)
def get_portal_summary(
    bucket: Literal["outstanding", "completed"] = Query("outstanding"),
    kind: PortalSummaryKind | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortalSummaryOut:
    rows: list[PortalSummaryRowOut] = list_portal_summary(db, user=user, bucket=bucket, kind=kind)
    return PortalSummaryOut(bucket=bucket, rows=rows)

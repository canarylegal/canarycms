"""Firm package status + catalogue detach (Phase 6 / firm schema ownership)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.firm_detach import detach, preflight_detach
from app.firm_package import evaluate_firm_package_status
from app.models import User

router = APIRouter(prefix="/firm-package", tags=["firm-package"])


class FirmPackageStatusOut(BaseModel):
    attached: bool
    compatible: bool
    fault: bool
    package_id: str | None = None
    package_version: str | None = None
    label: str | None = None
    requires_canary: str | None = None
    canary_version: str
    message: str | None = None
    detail: str | None = None
    mounts: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)


class FirmDetachBlockersOut(BaseModel):
    typed_cases: int = 0
    firm_case_state_rows: int = 0
    portal_submissions: int = 0
    module_schema: str | None = None
    blocked: bool = False


class FirmDetachResultOut(BaseModel):
    ok: bool
    forced: bool = False
    message: str = ""
    blockers: FirmDetachBlockersOut
    cleared: dict[str, int] = Field(default_factory=dict)


class FirmDetachRequest(BaseModel):
    """Force detach body. ``confirm`` must be true; sandboxes only."""

    force: bool = False
    confirm: bool = False


@router.get("/status", response_model=FirmPackageStatusOut)
def firm_package_status(_user: User = Depends(get_current_user)) -> FirmPackageStatusOut:
    """Staff-visible firm package attach / compatibility status."""
    return FirmPackageStatusOut.model_validate(evaluate_firm_package_status().as_dict())


@router.get("/detach/preflight", response_model=FirmDetachResultOut)
def firm_detach_preflight(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FirmDetachResultOut:
    """Report whether firm catalogue detach is blocked by dependents."""
    return FirmDetachResultOut.model_validate(preflight_detach(db).as_dict())


@router.post("/detach", response_model=FirmDetachResultOut)
def firm_detach(
    body: FirmDetachRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FirmDetachResultOut:
    """Detach firm catalogue.

    Without ``force``, succeeds only when preflight reports no blockers (then wipes
    unused catalogue). With ``force`` + ``confirm``, nulls case type FKs, deletes
    firm catalogue / portal submissions, clears branding, and drops module schemas.
    """
    result = detach(db, force=body.force, confirm=body.confirm if body.force else True)
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.as_dict())
    return FirmDetachResultOut.model_validate(result.as_dict())

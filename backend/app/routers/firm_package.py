"""Firm package status (Phase 6) — available to all authenticated staff."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
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


@router.get("/status", response_model=FirmPackageStatusOut)
def firm_package_status(_user: User = Depends(get_current_user)) -> FirmPackageStatusOut:
    """Staff-visible firm package attach / compatibility status."""
    return FirmPackageStatusOut.model_validate(evaluate_firm_package_status().as_dict())

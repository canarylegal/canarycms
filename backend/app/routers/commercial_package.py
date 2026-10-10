"""Commercial package attach status."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.commercial_package import evaluate_commercial_package_status
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/commercial-package", tags=["commercial-package"])


class CommercialPackageStatusOut(BaseModel):
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
    products: list[str] = Field(default_factory=list)
    loaded: bool = False


@router.get("/status", response_model=CommercialPackageStatusOut)
def commercial_package_status(_user: User = Depends(get_current_user)) -> CommercialPackageStatusOut:
    """Staff-visible commercial package attach / compatibility status."""
    return CommercialPackageStatusOut.model_validate(evaluate_commercial_package_status().as_dict())

"""Staff-readable optional-core capability flags (not full Admin firm settings)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.portal_case import firm_canary_sign_enabled, firm_client_portal_enabled

router = APIRouter(prefix="/firm-capabilities", tags=["firm-capabilities"])


class FirmCapabilitiesOut(BaseModel):
    client_portal_enabled: bool = True
    canary_sign_enabled: bool = True


@router.get("", response_model=FirmCapabilitiesOut)
def get_firm_capabilities(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FirmCapabilitiesOut:
    return FirmCapabilitiesOut(
        client_portal_enabled=firm_client_portal_enabled(db),
        canary_sign_enabled=firm_canary_sign_enabled(db),
    )

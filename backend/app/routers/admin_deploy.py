"""Admin-only: deployment status and GitHub update checks (notify-only; no in-app Compose update)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_admin
from app.github_update_check import build_update_check_payload
from app.models import User
from app.schemas import (
    AdminDeployStatusOut,
    AdminDeployTriggerIn,
    AdminDeployTriggerOut,
    AdminDeployUpdateCheckOut,
)

router = APIRouter(prefix="/admin/deploy", tags=["admin-deploy"])

_GUI_UPDATE_GONE = (
    "In-app Compose updates were removed for security (no Docker socket in the backend). "
    "Apply updates on the host via SSH or CI — see docs/DEPLOYMENT.md. "
    "Admin → Deploy can still check whether this install is behind GitHub."
)


def deploy_status_public() -> dict:
    return {
        "configured": False,
        "compose_update_enabled": False,
        "compose_git_reset_enabled": False,
        "compose_git_ref": (os.getenv("CANARY_GITHUB_DEPLOY_REF") or "main").strip() or "main",
    }


@router.get("/status", response_model=AdminDeployStatusOut)
def deploy_status(_admin: User = Depends(require_admin)) -> AdminDeployStatusOut:
    return AdminDeployStatusOut.model_validate(deploy_status_public())


@router.get("/update-check", response_model=AdminDeployUpdateCheckOut)
def deploy_update_check(_admin: User = Depends(require_admin)) -> AdminDeployUpdateCheckOut:
    return AdminDeployUpdateCheckOut.model_validate(build_update_check_payload())


@router.get("/compose-job")
def compose_job_status(_admin: User = Depends(require_admin)) -> dict:
    """Retired: GUI Compose updates are no longer available."""
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GUI_UPDATE_GONE)


@router.post("/trigger", response_model=AdminDeployTriggerOut)
def deploy_trigger(
    _body: AdminDeployTriggerIn = AdminDeployTriggerIn(),
    _admin: User = Depends(require_admin),
) -> AdminDeployTriggerOut:
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GUI_UPDATE_GONE)

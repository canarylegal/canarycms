"""Admin-only: trigger deployment via Docker Compose on the host (self-host)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.compose_deploy_job import get_compose_job_public, start_or_busy
from app.deps import require_admin
from app.github_update_check import build_update_check_payload
from app.local_compose_update import compose_update_configured
from app.models import User
from app.schemas import (
    AdminDeployComposeJobOut,
    AdminDeployStatusOut,
    AdminDeployTriggerIn,
    AdminDeployTriggerOut,
    AdminDeployUpdateCheckOut,
)

router = APIRouter(prefix="/admin/deploy", tags=["admin-deploy"])


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        return first or None
    if request.client:
        return request.client.host
    return None


def deploy_status_public() -> dict:
    co = compose_update_configured()
    return {
        "configured": co,
        "compose_update_enabled": co,
    }


def _enqueue_compose_trigger(request: Request, admin: User) -> AdminDeployTriggerOut:
    started = start_or_busy(
        actor_user_id=admin.id,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if started == "busy":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A Docker Compose update is already running. Wait for it to finish or open Admin → Deploy "
                "to watch status."
            ),
        )
    return AdminDeployTriggerOut(
        ok=True,
        async_mode=True,
        job_id=started.job_id,
        message="Compose update started in the background. The app will poll until it finishes.",
    )


@router.get("/status", response_model=AdminDeployStatusOut)
def deploy_status(_admin: User = Depends(require_admin)) -> AdminDeployStatusOut:
    return AdminDeployStatusOut.model_validate(deploy_status_public())


@router.get("/update-check", response_model=AdminDeployUpdateCheckOut)
def deploy_update_check(_admin: User = Depends(require_admin)) -> AdminDeployUpdateCheckOut:
    return AdminDeployUpdateCheckOut.model_validate(build_update_check_payload())


@router.get("/compose-job", response_model=AdminDeployComposeJobOut)
def compose_job_status(_admin: User = Depends(require_admin)) -> AdminDeployComposeJobOut:
    """Poll background compose update (returns immediately; run from Admin UI after POST /trigger)."""
    return AdminDeployComposeJobOut.model_validate(get_compose_job_public())


@router.post("/trigger", response_model=AdminDeployTriggerOut)
def deploy_trigger(
    request: Request,
    _body: AdminDeployTriggerIn = AdminDeployTriggerIn(),
    admin: User = Depends(require_admin),
) -> AdminDeployTriggerOut:
    co = compose_update_configured()
    if not co:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Docker Compose update is not enabled. Set CANARY_COMPOSE_UPDATE_ENABLED=1, "
                "CANARY_COMPOSE_PROJECT_DIR to the compose project on the host, mount "
                "/var/run/docker.sock and that directory into the backend — see .env.example."
            ),
        )
    return _enqueue_compose_trigger(request, admin)

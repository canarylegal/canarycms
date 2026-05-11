"""Admin-only: trigger deployment — Docker Compose on host (self-host default) or GitHub Actions."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import require_admin
from app.github_deploy import github_deploy_status_public, load_github_deploy_config, trigger_workflow_dispatch
from app.github_update_check import build_update_check_payload
from app.local_compose_update import compose_update_configured, run_compose_update
from app.models import User
from app.schemas import AdminDeployStatusOut, AdminDeployTriggerIn, AdminDeployTriggerOut, AdminDeployUpdateCheckOut

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
    gh = github_deploy_status_public()
    co = compose_update_configured()
    gh_ok = bool(gh.get("configured"))
    return {
        "configured": co or gh_ok,
        "compose_update_enabled": co,
        "github_actions_configured": gh_ok,
        "owner": gh["owner"],
        "repo": gh["repo"],
        "workflow": gh["workflow"],
        "default_ref": gh["default_ref"],
    }


def _run_compose_trigger(request: Request, admin: User, db: Session) -> AdminDeployTriggerOut:
    try:
        run_compose_update()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e) or "Docker Compose update failed",
        ) from e
    log_event(
        db,
        actor_user_id=admin.id,
        action="admin_compose_update",
        entity_type="docker_compose",
        entity_id="compose_pull_build_up",
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        meta={"profiles": (os.getenv("CANARY_COMPOSE_PROFILES") or "prod")},
    )
    return AdminDeployTriggerOut(
        ok=True,
        message="Docker Compose finished (git pull if enabled, build --pull, up -d). Refresh the app after containers restart.",
    )


def _trigger_github(
    request: Request,
    body: AdminDeployTriggerIn,
    admin: User,
    db: Session,
) -> AdminDeployTriggerOut:
    cfg = load_github_deploy_config()
    assert cfg is not None
    ref = body.ref
    env_label = (body.environment or "").strip() or "production"
    use_ref = (ref or "").strip() or cfg.default_ref
    try:
        trigger_workflow_dispatch(ref=use_ref, environment=env_label)
    except httpx.HTTPStatusError as e:
        msg = f"GitHub API HTTP {e.response.status_code}"
        try:
            data = e.response.json()
            if isinstance(data, dict) and data.get("message"):
                msg = str(data["message"])
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e) or "Failed to contact GitHub",
        ) from e

    log_event(
        db,
        actor_user_id=admin.id,
        action="admin_deploy_trigger",
        entity_type="github_workflow_dispatch",
        entity_id=f"{cfg.owner}/{cfg.repo}",
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        meta={"ref": use_ref, "environment": env_label, "workflow": cfg.workflow},
    )
    return AdminDeployTriggerOut(
        ok=True,
        message="Deployment workflow was requested. Check GitHub Actions on the repository for progress.",
    )


@router.get("/status", response_model=AdminDeployStatusOut)
def deploy_status(_admin: User = Depends(require_admin)) -> AdminDeployStatusOut:
    return AdminDeployStatusOut.model_validate(deploy_status_public())


@router.get("/update-check", response_model=AdminDeployUpdateCheckOut)
def deploy_update_check(_admin: User = Depends(require_admin)) -> AdminDeployUpdateCheckOut:
    return AdminDeployUpdateCheckOut.model_validate(build_update_check_payload())


@router.post("/trigger", response_model=AdminDeployTriggerOut)
def deploy_trigger(
    request: Request,
    body: AdminDeployTriggerIn = AdminDeployTriggerIn(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminDeployTriggerOut:
    co = compose_update_configured()
    gh_ok = load_github_deploy_config() is not None
    method = body.method

    if method == "compose":
        if not co:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Docker Compose update is not enabled. Set CANARY_COMPOSE_UPDATE_ENABLED=1, "
                    "CANARY_COMPOSE_PROJECT_DIR to the compose project on the host, mount "
                    "/var/run/docker.sock and that directory into the backend — see .env.example."
                ),
            )
        return _run_compose_trigger(request, admin, db)

    if method == "github":
        if not gh_ok:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub deploy is not configured. Set CANARY_GITHUB_DEPLOY_TOKEN, OWNER, and REPO on the server.",
            )
        return _trigger_github(request, body, admin, db)

    # auto: prefer Compose for self-host parity with GUI expectations
    if co:
        return _run_compose_trigger(request, admin, db)
    if gh_ok:
        return _trigger_github(request, body, admin, db)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "No deploy path configured. For typical self-hosting set CANARY_COMPOSE_UPDATE_ENABLED=1 and "
            "CANARY_COMPOSE_PROJECT_DIR (see .env.example), or set CANARY_GITHUB_DEPLOY_* for GitHub Actions."
        ),
    )

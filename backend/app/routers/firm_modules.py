"""Firm module APIs (Phase 4 — published slots, UI bundle, lifecycle contract)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.firm_module_runtime import (
    ensure_case_state,
    load_manifest,
    module_applies_to_case,
    pipeline_summary,
    resolve_ui_asset,
    slots_enabled,
    ui_section,
)
from app.models import FirmModuleCaseState, User

router = APIRouter(prefix="/firm-modules", tags=["firm-modules"])


class FirmModuleUiOut(BaseModel):
    """Build-time firm UI bundle metadata (served from FIRM_MODULE_DIR)."""

    bundle_url: str | None = None
    exports: dict[str, str] = Field(default_factory=dict)


class FirmModuleManifestOut(BaseModel):
    enabled: bool
    module_id: str | None = None
    label: str | None = None
    panel_label: str | None = None
    requires_canary: str | None = None
    stages: list[str] = Field(default_factory=list)
    checklist_labels: list[str] = Field(default_factory=list)
    attr_fields: list[dict[str, Any]] = Field(default_factory=list)
    matter_head_type_name: str | None = None
    matter_sub_type_names: list[str] = Field(default_factory=list)
    slots: dict[str, bool] = Field(default_factory=dict)
    ui: FirmModuleUiOut | None = None


class FirmModuleCaseStateOut(BaseModel):
    module_id: str
    case_id: uuid.UUID
    stage: str = ""
    stages: list[str] = Field(default_factory=list)
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)
    integration: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class FirmModuleCaseStateUpdate(BaseModel):
    stage: str | None = None
    checklist: list[dict[str, Any]] | None = None
    attrs: dict[str, Any] | None = None


class FirmModulePipelineOut(BaseModel):
    enabled: bool
    module_id: str | None = None
    label: str | None = None
    by_stage: dict[str, int] = Field(default_factory=dict)
    unstaged: int = 0
    total: int = 0


def _require_manifest() -> dict[str, Any]:
    manifest = load_manifest()
    if not manifest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No firm module attached")
    return manifest


def _ui_out(manifest: dict[str, Any]) -> FirmModuleUiOut | None:
    ui = ui_section(manifest)
    if not ui:
        return None
    exports_raw = ui.get("exports") if isinstance(ui.get("exports"), dict) else {}
    exports = {str(k): str(v) for k, v in exports_raw.items() if k and v}
    bundle = str(ui.get("bundle") or "ui/dist/firm-module.js").strip()
    # Public path relative to API — host loads via /firm-modules/active/ui/…
    filename = bundle.rsplit("/", 1)[-1] if bundle else "firm-module.js"
    return FirmModuleUiOut(
        bundle_url=f"/firm-modules/active/ui/{filename}",
        exports=exports,
    )


@router.get("/active", response_model=FirmModuleManifestOut)
def get_active_module(_user: User = Depends(get_current_user)) -> FirmModuleManifestOut:
    manifest = load_manifest()
    if not manifest:
        return FirmModuleManifestOut(enabled=False)
    return FirmModuleManifestOut(
        enabled=True,
        module_id=str(manifest.get("module_id") or ""),
        label=str(manifest.get("label") or ""),
        panel_label=str(manifest.get("panel_label") or manifest.get("label") or "Firm module"),
        requires_canary=str(manifest.get("requires_canary") or ""),
        stages=[str(s) for s in (manifest.get("stages") or [])],
        checklist_labels=[str(s) for s in (manifest.get("checklist") or [])],
        attr_fields=list(manifest.get("attr_fields") or []),
        matter_head_type_name=(manifest.get("matter_head_type_name") or None),
        matter_sub_type_names=[str(s) for s in (manifest.get("matter_sub_type_names") or [])],
        slots=slots_enabled(manifest),
        ui=_ui_out(manifest),
    )


@router.get("/active/pipeline", response_model=FirmModulePipelineOut)
def get_pipeline(_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FirmModulePipelineOut:
    manifest = load_manifest()
    if not manifest:
        return FirmModulePipelineOut(enabled=False)
    summary = pipeline_summary(db, manifest)
    return FirmModulePipelineOut(enabled=True, **summary)


@router.get("/active/ui/{asset_path:path}")
def get_ui_asset(asset_path: str) -> FileResponse:
    """Serve the firm package UI bundle (same-origin, build-time artifact — not remote JS).

    Unauthenticated: the bundle contains no matter data; APIs remain token-gated.
    """
    path = resolve_ui_asset(asset_path)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firm UI asset not found")
    media = "application/javascript" if path.suffix in {".js", ".mjs"} else None
    if path.suffix == ".css":
        media = "text/css"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "no-cache"})


@router.get("/active/matters/{case_id}", response_model=FirmModuleCaseStateOut)
def get_case_state(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FirmModuleCaseStateOut:
    require_case_access(case_id, user, db)
    manifest = _require_manifest()
    if not module_applies_to_case(db, manifest, case_id=case_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firm module does not apply to this matter")
    module_id = str(manifest["module_id"])
    row = ensure_case_state(db, module_id=module_id, case_id=case_id, manifest=manifest)
    db.commit()
    db.refresh(row)
    return _state_out(row)


@router.put("/active/matters/{case_id}", response_model=FirmModuleCaseStateOut)
def put_case_state(
    case_id: uuid.UUID,
    payload: FirmModuleCaseStateUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FirmModuleCaseStateOut:
    require_case_access(case_id, user, db)
    manifest = _require_manifest()
    if not module_applies_to_case(db, manifest, case_id=case_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firm module does not apply to this matter")
    module_id = str(manifest["module_id"])
    row = ensure_case_state(db, module_id=module_id, case_id=case_id, manifest=manifest)
    data = dict(row.payload or {})
    if payload.stage is not None:
        data["stage"] = payload.stage.strip()
    if payload.checklist is not None:
        data["checklist"] = payload.checklist
    if payload.attrs is not None:
        data["attrs"] = payload.attrs
    row.payload = data
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _state_out(row)


def _state_out(row: FirmModuleCaseState) -> FirmModuleCaseStateOut:
    p = row.payload or {}
    return FirmModuleCaseStateOut(
        module_id=row.module_id,
        case_id=row.case_id,
        stage=str(p.get("stage") or ""),
        stages=[str(s) for s in (p.get("stages") or [])],
        checklist=list(p.get("checklist") or []),
        attrs=dict(p.get("attrs") or {}),
        integration=dict(p.get("integration") or {}),
        updated_at=row.updated_at,
    )

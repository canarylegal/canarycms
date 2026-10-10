"""Commercial module APIs — active manifest + UI bundle serve."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.commercial_module_runtime import load_manifest, resolve_ui_asset, slots_enabled, ui_section
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/commercial-modules", tags=["commercial-modules"])


class CommercialModuleUiOut(BaseModel):
    bundle_url: str | None = None
    exports: dict[str, str] = Field(default_factory=dict)


class CommercialModuleManifestOut(BaseModel):
    enabled: bool
    module_id: str | None = None
    label: str | None = None
    requires_canary: str | None = None
    products: list[str] = Field(default_factory=list)
    slots: dict[str, bool] = Field(default_factory=dict)
    ui: CommercialModuleUiOut | None = None


def _ui_out(manifest: dict[str, Any]) -> CommercialModuleUiOut | None:
    ui = ui_section(manifest)
    if not ui:
        return None
    exports_raw = ui.get("exports") if isinstance(ui.get("exports"), dict) else {}
    exports = {str(k): str(v) for k, v in exports_raw.items() if k and v}
    bundle = str(ui.get("bundle") or "ui/dist/commercial-module.js").strip()
    filename = bundle.rsplit("/", 1)[-1] if bundle else "commercial-module.js"
    return CommercialModuleUiOut(
        bundle_url=f"/commercial-modules/active/ui/{filename}",
        exports=exports,
    )


@router.get("/active", response_model=CommercialModuleManifestOut)
def get_active_module(_user: User = Depends(get_current_user)) -> CommercialModuleManifestOut:
    manifest = load_manifest()
    if not manifest:
        return CommercialModuleManifestOut(enabled=False)
    products = [str(p) for p in (manifest.get("products") or []) if str(p).strip()]
    if not products:
        # Fall back to package-level products
        from app.commercial_package import evaluate_commercial_package_status

        products = list(evaluate_commercial_package_status().products)
    return CommercialModuleManifestOut(
        enabled=True,
        module_id=str(manifest.get("module_id") or ""),
        label=str(manifest.get("label") or ""),
        requires_canary=str(manifest.get("requires_canary") or ""),
        products=products,
        slots=slots_enabled(manifest),
        ui=_ui_out(manifest),
    )


@router.get("/active/ui/{asset_path:path}")
def get_active_ui_asset(asset_path: str) -> FileResponse:
    """Serve commercial UI bundle assets (unauthenticated; no matter data)."""
    path = resolve_ui_asset(asset_path)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UI asset not found")
    media = "application/javascript" if path.suffix in {".js", ".mjs"} else None
    if path.suffix == ".css":
        media = "text/css"
    return FileResponse(
        path,
        media_type=media,
        headers={"Cache-Control": "no-cache"},
    )

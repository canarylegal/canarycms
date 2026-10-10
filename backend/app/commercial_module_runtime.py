"""Load commercial module manifest + resolve UI assets from COMMERCIAL_MODULE_DIR."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SLOT_ADMIN_INTEGRATIONS = "admin_integrations"
SLOT_MATTER_SEARCHES = "matter_searches"
SLOT_MATTER_LAND_REGISTRY = "matter_land_registry"
SLOT_APP_DOCUSIGN = "app_docusign"
SLOT_MODAL_SEND_DOCUSIGN = "modal_send_docusign"

_ALL_SLOTS = (
    SLOT_ADMIN_INTEGRATIONS,
    SLOT_MATTER_SEARCHES,
    SLOT_MATTER_LAND_REGISTRY,
    SLOT_APP_DOCUSIGN,
    SLOT_MODAL_SEND_DOCUSIGN,
)

_manifest_cache: dict[str, Any] | None = None
_manifest_mtime: float | None = None


def commercial_module_dir() -> Path | None:
    raw = (os.getenv("COMMERCIAL_MODULE_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_dir():
            return path
    candidate = Path("/commercial/module")
    if candidate.is_dir():
        return candidate
    # Infer from package root
    from app.commercial_package import commercial_package_dir

    root = commercial_package_dir()
    if root is not None:
        module = root / "module"
        if module.is_dir():
            return module
    return None


def load_manifest(*, force: bool = False) -> dict[str, Any] | None:
    """Return commercial module manifest, or None if package absent/incompatible."""
    global _manifest_cache, _manifest_mtime
    from app.commercial_package import commercial_package_allows

    if not commercial_package_allows(force=force):
        _manifest_cache = None
        _manifest_mtime = None
        return None
    directory = commercial_module_dir()
    if directory is None:
        _manifest_cache = None
        _manifest_mtime = None
        return None
    path = directory / "manifest.json"
    if not path.is_file():
        return None
    mtime = path.stat().st_mtime
    if not force and _manifest_cache is not None and _manifest_mtime == mtime:
        return _manifest_cache
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported commercial module manifest version: %s", raw.get("version"))
        return None
    module_id = (raw.get("module_id") or "").strip()
    if not module_id:
        log.warning("Commercial module manifest missing module_id")
        return None
    _manifest_cache = raw
    _manifest_mtime = mtime
    return raw


def ui_section(manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    m = manifest if manifest is not None else load_manifest()
    if not m:
        return None
    ui = m.get("ui")
    return ui if isinstance(ui, dict) else None


def storage_schema(manifest: dict[str, Any] | None = None) -> str | None:
    m = manifest if manifest is not None else load_manifest()
    if not m:
        return None
    storage = m.get("storage") if isinstance(m.get("storage"), dict) else {}
    raw = str(storage.get("schema") or "").strip()
    return raw or None


def resolve_ui_asset(rel_path: str) -> Path | None:
    directory = commercial_module_dir()
    if directory is None:
        return None
    ui = ui_section()
    bundle_rel = ""
    if ui and isinstance(ui.get("bundle"), str) and ui["bundle"].strip():
        bundle_rel = ui["bundle"].strip().lstrip("/")
    base = (directory / Path(bundle_rel).parent) if bundle_rel else (directory / "ui" / "dist")
    try:
        base_resolved = base.resolve()
    except OSError:
        return None
    if not base_resolved.is_dir():
        return None
    candidate = (base_resolved / rel_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def slots_enabled(manifest: dict[str, Any]) -> dict[str, bool]:
    ui = ui_section(manifest) or {}
    exports = ui.get("exports") if isinstance(ui.get("exports"), dict) else {}
    declared = manifest.get("slots")
    out: dict[str, bool] = {s: False for s in _ALL_SLOTS}
    if isinstance(declared, dict):
        for key in _ALL_SLOTS:
            if key in declared:
                out[key] = bool(declared[key])
        return out
    for key in _ALL_SLOTS:
        out[key] = bool(exports.get(key))
    return out

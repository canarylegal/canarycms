"""Firm package root manifest (``canary-firm.json``) + Canary compatibility gate (Phase 6)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.canary_version import canary_product_version, version_satisfies

log = logging.getLogger(__name__)

_PACKAGE_CACHE: dict[str, Any] | None = None
_PACKAGE_MTIME: float | None = None
_STATUS_CACHE: "FirmPackageStatus | None" = None


@dataclass(frozen=True)
class FirmPackageStatus:
    """Public/staff-safe firm package attach status."""

    attached: bool
    compatible: bool
    fault: bool
    package_id: str | None
    package_version: str | None
    label: str | None
    requires_canary: str | None
    canary_version: str
    message: str | None
    detail: str | None
    mounts: list[str]
    modules: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "attached": self.attached,
            "compatible": self.compatible,
            "fault": self.fault,
            "package_id": self.package_id,
            "package_version": self.package_version,
            "label": self.label,
            "requires_canary": self.requires_canary,
            "canary_version": self.canary_version,
            "message": self.message,
            "detail": self.detail,
            "mounts": list(self.mounts),
            "modules": list(self.modules),
        }


def firm_package_dir() -> Path | None:
    """Directory containing ``canary-firm.json`` (package root)."""
    raw = (os.getenv("FIRM_PACKAGE_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_dir():
            return path
    # Compose mounts the package at /firm
    candidate = Path("/firm")
    if candidate.is_dir() and (candidate / "canary-firm.json").is_file():
        return candidate
    # Infer from FIRM_MODULE_DIR (.../module → parent)
    module_raw = (os.getenv("FIRM_MODULE_DIR") or "").strip()
    module = Path(module_raw).expanduser() if module_raw else Path("/firm/module")
    if module.is_dir():
        parent = module.parent
        if (parent / "canary-firm.json").is_file():
            return parent
    return None


def load_package_manifest(*, force: bool = False) -> dict[str, Any] | None:
    global _PACKAGE_CACHE, _PACKAGE_MTIME, _STATUS_CACHE
    directory = firm_package_dir()
    if directory is None:
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = None
        if force:
            _STATUS_CACHE = None
        return None
    path = directory / "canary-firm.json"
    if not path.is_file():
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = None
        return None
    mtime = path.stat().st_mtime
    if not force and _PACKAGE_CACHE is not None and _PACKAGE_MTIME == mtime:
        return _PACKAGE_CACHE
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported canary-firm.json version: %s", raw.get("version"))
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = mtime
        _STATUS_CACHE = None
        return None
    package_id = (raw.get("package_id") or "").strip()
    if not package_id:
        log.warning("canary-firm.json missing package_id")
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = mtime
        _STATUS_CACHE = None
        return None
    _PACKAGE_CACHE = raw
    _PACKAGE_MTIME = mtime
    _STATUS_CACHE = None
    return raw


def evaluate_firm_package_status(*, force: bool = False) -> FirmPackageStatus:
    """Evaluate attach + compatibility. Cached until manifest mtime changes or force=True."""
    global _STATUS_CACHE
    if not force and _STATUS_CACHE is not None:
        return _STATUS_CACHE

    canary_ver = canary_product_version()
    manifest = load_package_manifest(force=force)
    if not manifest:
        # Package dir mounted without canary-firm.json still counts as a soft fault if /firm exists
        directory = firm_package_dir()
        if directory is not None and not (directory / "canary-firm.json").is_file():
            status = FirmPackageStatus(
                attached=True,
                compatible=False,
                fault=True,
                package_id=None,
                package_version=None,
                label=None,
                requires_canary=None,
                canary_version=canary_ver,
                message="Firm package incompatible",
                detail="canary-firm.json missing — firm features disabled until a package manifest is present.",
                mounts=[],
                modules=[],
            )
            _STATUS_CACHE = status
            return status
        status = FirmPackageStatus(
            attached=False,
            compatible=True,
            fault=False,
            package_id=None,
            package_version=None,
            label=None,
            requires_canary=None,
            canary_version=canary_ver,
            message=None,
            detail=None,
            mounts=[],
            modules=[],
        )
        _STATUS_CACHE = status
        return status

    requires = str(manifest.get("requires_canary") or "").strip() or ">=0.0.0"
    package_id = str(manifest.get("package_id") or "")
    package_version = str(manifest.get("package_version") or "").strip() or None
    label = str(manifest.get("label") or package_id).strip() or package_id
    mounts = [str(m) for m in (manifest.get("mounts") or []) if str(m).strip()]
    modules = [str(m) for m in (manifest.get("modules") or []) if str(m).strip()]

    try:
        ok = version_satisfies(canary_ver, requires)
    except ValueError as exc:
        status = FirmPackageStatus(
            attached=True,
            compatible=False,
            fault=True,
            package_id=package_id,
            package_version=package_version,
            label=label,
            requires_canary=requires,
            canary_version=canary_ver,
            message="Firm package incompatible",
            detail=f"Invalid requires_canary {requires!r}: {exc}",
            mounts=mounts,
            modules=modules,
        )
        _STATUS_CACHE = status
        log.error("firm_package compat: %s", status.detail)
        return status

    if not ok:
        detail = (
            f"{label} {package_version or '(unversioned)'} requires Canary {requires}; "
            f"this install is {canary_ver}. Firm features are disabled."
        )
        status = FirmPackageStatus(
            attached=True,
            compatible=False,
            fault=True,
            package_id=package_id,
            package_version=package_version,
            label=label,
            requires_canary=requires,
            canary_version=canary_ver,
            message="Firm package incompatible",
            detail=detail,
            mounts=mounts,
            modules=modules,
        )
        _STATUS_CACHE = status
        log.error("firm_package: %s", detail)
        return status

    status = FirmPackageStatus(
        attached=True,
        compatible=True,
        fault=False,
        package_id=package_id,
        package_version=package_version,
        label=label,
        requires_canary=requires,
        canary_version=canary_ver,
        message=None,
        detail=None,
        mounts=mounts,
        modules=modules,
    )
    _STATUS_CACHE = status
    return status


def firm_package_allows_module(*, force: bool = False) -> bool:
    """True when a firm module may load (package compatible or no package attached)."""
    status = evaluate_firm_package_status(force=force)
    if not status.attached:
        # No package manifest — module-only attach still allowed (legacy Phase 3/4 mounts).
        return True
    return status.compatible

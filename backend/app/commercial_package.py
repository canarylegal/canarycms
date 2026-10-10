"""Commercial package root manifest (``canary-commercial.json``) + compatibility gate."""

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
_STATUS_CACHE: "CommercialPackageStatus | None" = None


@dataclass(frozen=True)
class CommercialPackageStatus:
    """Staff-safe commercial package attach status."""

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
    products: list[str]
    loaded: bool

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
            "products": list(self.products),
            "loaded": self.loaded,
        }


def commercial_package_dir() -> Path | None:
    """Directory containing ``canary-commercial.json`` (package root)."""
    raw = (os.getenv("COMMERCIAL_PACKAGE_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_dir():
            return path
    candidate = Path("/commercial")
    if candidate.is_dir() and (candidate / "canary-commercial.json").is_file():
        return candidate
    return None


def commercial_python_dir() -> Path | None:
    """Directory to add to ``sys.path`` (contains ``canary_commercial`` package)."""
    root = commercial_package_dir()
    if root is None:
        return None
    python_dir = root / "python"
    if (python_dir / "canary_commercial").is_dir():
        return python_dir
    return None


def load_package_manifest(*, force: bool = False) -> dict[str, Any] | None:
    global _PACKAGE_CACHE, _PACKAGE_MTIME, _STATUS_CACHE
    directory = commercial_package_dir()
    if directory is None:
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = None
        if force:
            _STATUS_CACHE = None
        return None
    path = directory / "canary-commercial.json"
    if not path.is_file():
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = None
        return None
    mtime = path.stat().st_mtime
    if not force and _PACKAGE_CACHE is not None and _PACKAGE_MTIME == mtime:
        return _PACKAGE_CACHE
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported canary-commercial.json version: %s", raw.get("version"))
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = mtime
        _STATUS_CACHE = None
        return None
    package_id = (raw.get("package_id") or "").strip()
    if not package_id:
        log.warning("canary-commercial.json missing package_id")
        _PACKAGE_CACHE = None
        _PACKAGE_MTIME = mtime
        _STATUS_CACHE = None
        return None
    _PACKAGE_CACHE = raw
    _PACKAGE_MTIME = mtime
    _STATUS_CACHE = None
    return raw


def evaluate_commercial_package_status(*, force: bool = False) -> CommercialPackageStatus:
    """Evaluate attach + compatibility. Cached until manifest mtime changes or force=True."""
    global _STATUS_CACHE
    from app.commercial_runtime import commercial_loaded

    if not force and _STATUS_CACHE is not None:
        # ``loaded`` flips after router registration — refresh that field only.
        cached = _STATUS_CACHE
        loaded_now = commercial_loaded()
        if cached.loaded == loaded_now:
            return cached
        refreshed = CommercialPackageStatus(
            attached=cached.attached,
            compatible=cached.compatible,
            fault=cached.fault,
            package_id=cached.package_id,
            package_version=cached.package_version,
            label=cached.label,
            requires_canary=cached.requires_canary,
            canary_version=cached.canary_version,
            message=cached.message,
            detail=cached.detail,
            mounts=list(cached.mounts),
            products=list(cached.products),
            loaded=loaded_now,
        )
        _STATUS_CACHE = refreshed
        return refreshed

    canary_ver = canary_product_version()
    manifest = load_package_manifest(force=force)
    if not manifest:
        directory = commercial_package_dir()
        if directory is not None and not (directory / "canary-commercial.json").is_file():
            status = CommercialPackageStatus(
                attached=True,
                compatible=False,
                fault=True,
                package_id=None,
                package_version=None,
                label=None,
                requires_canary=None,
                canary_version=canary_ver,
                message="Commercial package incompatible",
                detail="canary-commercial.json missing — commercial features disabled.",
                mounts=[],
                products=[],
                loaded=False,
            )
            _STATUS_CACHE = status
            return status
        status = CommercialPackageStatus(
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
            products=[],
            loaded=False,
        )
        _STATUS_CACHE = status
        return status

    requires = str(manifest.get("requires_canary") or "").strip() or ">=0.0.0"
    package_id = str(manifest.get("package_id") or "")
    package_version = str(manifest.get("package_version") or "").strip() or None
    label = str(manifest.get("label") or package_id).strip() or package_id
    mounts = [str(m) for m in (manifest.get("mounts") or []) if str(m).strip()]
    products = [str(p) for p in (manifest.get("products") or []) if str(p).strip()]

    try:
        ok = version_satisfies(canary_ver, requires)
    except ValueError as exc:
        status = CommercialPackageStatus(
            attached=True,
            compatible=False,
            fault=True,
            package_id=package_id,
            package_version=package_version,
            label=label,
            requires_canary=requires,
            canary_version=canary_ver,
            message="Commercial package incompatible",
            detail=f"Invalid requires_canary {requires!r}: {exc}",
            mounts=mounts,
            products=products,
            loaded=False,
        )
        _STATUS_CACHE = status
        log.error("commercial_package compat: %s", status.detail)
        return status

    if not ok:
        detail = (
            f"{label} {package_version or '(unversioned)'} requires Canary {requires}; "
            f"this install is {canary_ver}. Commercial features are disabled."
        )
        status = CommercialPackageStatus(
            attached=True,
            compatible=False,
            fault=True,
            package_id=package_id,
            package_version=package_version,
            label=label,
            requires_canary=requires,
            canary_version=canary_ver,
            message="Commercial package incompatible",
            detail=detail,
            mounts=mounts,
            products=products,
            loaded=False,
        )
        _STATUS_CACHE = status
        log.error("commercial_package: %s", detail)
        return status

    status = CommercialPackageStatus(
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
        products=products,
        loaded=commercial_loaded(),
    )
    _STATUS_CACHE = status
    return status


def commercial_package_allows(*, force: bool = False) -> bool:
    """True when commercial connectors may load."""
    status = evaluate_commercial_package_status(force=force)
    return status.attached and status.compatible

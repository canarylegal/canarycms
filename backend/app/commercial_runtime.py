"""Load the commercial Python package onto ``sys.path`` and register routers."""

from __future__ import annotations

import importlib
import logging
import sys
from types import ModuleType
from typing import Any

log = logging.getLogger(__name__)

_LOADED = False
_LOAD_ATTEMPTED = False
_REGISTERED_PRODUCTS: list[str] = []


def commercial_loaded() -> bool:
    return _LOADED


def registered_products() -> list[str]:
    return list(_REGISTERED_PRODUCTS)


def ensure_commercial_path() -> bool:
    """Add commercial ``python/`` to ``sys.path`` when the package is allowed.

    Returns True when ``canary_commercial`` is importable afterwards.
    """
    global _LOAD_ATTEMPTED, _LOADED
    if _LOADED:
        return True
    if _LOAD_ATTEMPTED and not _LOADED:
        return False
    _LOAD_ATTEMPTED = True

    from app.commercial_package import commercial_package_allows, commercial_python_dir

    if not commercial_package_allows():
        return False
    python_dir = commercial_python_dir()
    if python_dir is None:
        log.warning("commercial package attached but python/canary_commercial missing")
        return False
    path_str = str(python_dir)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
    try:
        importlib.import_module("canary_commercial")
    except Exception:
        log.exception("failed to import canary_commercial from %s", path_str)
        return False
    _LOADED = True
    return True


def import_commercial(module: str) -> ModuleType | None:
    """Import ``canary_commercial…`` when the package is loaded; else None."""
    if not ensure_commercial_path():
        return None
    try:
        return importlib.import_module(module)
    except Exception:
        log.exception("failed to import %s", module)
        return None


def register_commercial_routers(app: Any) -> list[str]:
    """Register commercial routers on the FastAPI app when attached + compatible."""
    global _REGISTERED_PRODUCTS
    if not ensure_commercial_path():
        log.info("commercial package not loaded — DocuSign/Casera/HMLR routers omitted")
        _REGISTERED_PRODUCTS = []
        return []
    mod = importlib.import_module("canary_commercial.register")
    products = list(mod.register(app) or [])
    _REGISTERED_PRODUCTS = products
    return products


def reexport_commercial(globals_dict: dict[str, Any], module_name: str) -> bool:
    """Copy public attrs from a commercial module into a Core shim module.

    Returns True when the commercial module was loaded.
    """
    mod = import_commercial(module_name)
    if mod is None:
        return False
    for name, value in vars(mod).items():
        if name.startswith("_"):
            continue
        globals_dict[name] = value
    globals_dict["__doc__"] = getattr(mod, "__doc__", globals_dict.get("__doc__"))
    return True

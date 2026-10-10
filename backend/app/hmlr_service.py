"""Core shim — implementation lives in canary-commercial when attached."""

from __future__ import annotations

from app.commercial_runtime import reexport_commercial

if not reexport_commercial(globals(), "canary_commercial.hmlr_service"):
    raise ImportError(
        "hmlr_service requires the Canary commercial package "
        "(set COMMERCIAL_PACKAGE_DIR / attach docker-compose.commercial.example.yml)."
    )

"""Core shim — implementation lives in canary-commercial when attached."""

from __future__ import annotations

from app.commercial_runtime import reexport_commercial

if not reexport_commercial(globals(), "canary_commercial.hmlr_settings"):
    pass  # commercial not attached — callers must gate on package status

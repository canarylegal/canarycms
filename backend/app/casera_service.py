"""Core shim — Casera service (commercial package when attached)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.commercial_runtime import reexport_commercial

if not reexport_commercial(globals(), "canary_commercial.casera_service"):

    def search_file_summaries_for_case(db: Session, case_id: uuid.UUID) -> dict:  # type: ignore[no-redef]
        return {}

    def build_placeholder_pdf(*args, **kwargs) -> bytes:  # type: ignore[no-redef]
        raise RuntimeError("Casera is not available (commercial package not attached)")

    def normalize_risk_badges(*args, **kwargs):  # type: ignore[no-redef]
        return []

    def status_label(*args, **kwargs) -> str:  # type: ignore[no-redef]
        return ""

"""Firm-package matter type catalogue from ``FIRM_MATTER_TYPES_SEED_DIR``.

Looks for ``seed.json`` (same shape as the former product seed) under the env dir.
Unset / missing = skip (core no longer ships a catalogue).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.matter_type_bootstrap import sync_matter_types_from_path

log = logging.getLogger(__name__)


def _seed_path_from_env() -> Path | None:
    raw = (os.getenv("FIRM_MATTER_TYPES_SEED_DIR") or "").strip()
    if not raw:
        return None
    directory = Path(raw).expanduser()
    path = directory / "seed.json" if directory.is_dir() else directory
    return path if path.is_file() else None


def sync_matter_types_from_firm_seed(db: Session) -> bool:
    path = _seed_path_from_env()
    if path is None:
        log.info("FIRM_MATTER_TYPES_SEED_DIR unset or seed.json missing — skipping firm matter types.")
        return False
    return sync_matter_types_from_path(db, path)

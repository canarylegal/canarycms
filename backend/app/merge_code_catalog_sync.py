"""Insert missing rows into ``merge_code_catalog`` from canonical ``PRECEDENT_CODES``."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import MergeCodeCatalog

log = logging.getLogger(__name__)


def sync_merge_code_catalog(db: Session) -> None:
    """Add catalog rows for any code present in ``docx_util.PRECEDENT_CODES`` but not in the DB.

    Does not overwrite existing descriptions (admin edits preserved).
    """
    from app.docx_util import PRECEDENT_CODES

    added = 0
    for i, (code, desc) in enumerate(PRECEDENT_CODES.items()):
        if len(code) > 160:
            log.warning("merge_code_catalog: skip oversize code (%s chars)", len(code))
            continue
        row = db.get(MergeCodeCatalog, code)
        if row is None:
            db.add(MergeCodeCatalog(code=code, description=desc, sort_order=i))
            added += 1
    if added:
        db.commit()
        log.info("merge_code_catalog: inserted %s new code rows", added)

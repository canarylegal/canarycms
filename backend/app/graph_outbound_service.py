"""Optional Microsoft Graph enrichment for filed mail (OWA ``webLink``, etc.).

The public experimental stack may call Graph here to backfill ``outlook_web_link``.
This deployment keeps no-op stubs so uploads and ``outlook-open-hints`` stay stable;
extend with ``httpx`` + app credentials when ``CANARY_MS_GRAPH_*`` env vars are set.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.graph_mail import graph_mail_configured
from app.graph_outlook_categories import (
    resolve_outlook_owa_link_via_conversation,
    resolve_outlook_owa_link_via_graph,
)
from app.owa_urls import is_canary_synthetic_message_id
from app.models import File as DbFile
from app.models import User

log = logging.getLogger(__name__)


def link_outlook_graph_metadata_for_eml_file(db: Session, row: DbFile, abs_path: Path) -> None:
    """Hook after a parent ``.eml`` is written. Graph metadata may be filled later."""
    _ = (db, row, abs_path)


def repair_outlook_web_link_on_file(db: Session, row: DbFile) -> None:
    """Best-effort backfill of ``outlook_web_link`` from Graph when server is configured."""
    if row.outlook_web_link and str(row.outlook_web_link).strip():
        return
    if not graph_mail_configured(db):
        return

    owner = db.get(User, row.owner_id)
    if owner is None or not (owner.email or "").strip():
        return

    mid = (row.outlook_graph_message_id or row.source_outlook_item_id or "").strip()
    conv = (row.source_outlook_conversation_id or "").strip()
    if not mid and conv and is_canary_synthetic_message_id(row.source_internet_message_id):
        try:
            wl, gid = resolve_outlook_owa_link_via_conversation(owner.email.strip(), conv, db=db)
        except Exception:
            log.warning("repair_outlook_web_link_on_file: conversation lookup failed", exc_info=True)
            return
        if not wl and not gid:
            return
        if wl:
            row.outlook_web_link = wl
        if gid:
            from app.owa_urls import outlook_graph_message_id_storable

            row.source_outlook_item_id = gid
            storable = outlook_graph_message_id_storable(gid)
            if storable:
                row.outlook_graph_message_id = storable
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        return

    if not mid:
        return

    imid = (row.source_internet_message_id or "").strip() or None
    try:
        wl, resolved_gid = resolve_outlook_owa_link_via_graph(owner.email.strip(), mid, imid, db=db)
    except Exception:
        log.warning("repair_outlook_web_link_on_file: Graph lookup failed", exc_info=True)
        return

    if not wl:
        return

    row.outlook_web_link = wl
    if resolved_gid:
        from app.owa_urls import outlook_graph_message_id_storable

        row.source_outlook_item_id = resolved_gid
        storable = outlook_graph_message_id_storable(resolved_gid)
        if storable:
            row.outlook_graph_message_id = storable
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()

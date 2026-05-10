"""Seed and sync matter head / sub types and sub-menus from Canary ``seed.json``.

Head matter type **names** are canonical (defined in ``matter_types_seed/seed.json``).
On each startup we **merge** any missing heads, sub-types, and menus from the seed
without removing firm-specific rows. Admins cannot create or rename head types via API;
they may only hide heads the firm does not use.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MatterHeadType, MatterSubType, MatterSubTypeMenu

log = logging.getLogger(__name__)

SEED_PATH = Path(__file__).parent.parent / "matter_types_seed" / "seed.json"


def sync_matter_types_from_seed(db: Session) -> bool:
    """Apply or merge matter types from ``seed.json``. Returns True if the file was read and processed."""

    if not SEED_PATH.is_file():
        log.info("No matter type seed at %s — skipping.", SEED_PATH)
        return False

    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        log.warning("Unsupported matter type seed version: %s", raw.get("version"))
        return False

    matter_types = raw.get("matter_types") or []
    if not matter_types:
        log.info("Matter type seed is empty — skipping.")
        return False

    now = datetime.now(timezone.utc)
    try:
        for ht in matter_types:
            head_name = (ht.get("name") or "").strip()
            if not head_name:
                continue
            head = db.execute(select(MatterHeadType).where(MatterHeadType.name == head_name)).scalar_one_or_none()
            if not head:
                head_id = uuid.uuid4()
                db.add(
                    MatterHeadType(
                        id=head_id,
                        name=head_name,
                        is_hidden=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.flush()
                head = db.get(MatterHeadType, head_id)
            if not head:
                continue

            for st in ht.get("sub_types") or []:
                sub_name = (st.get("name") or "").strip()
                if not sub_name:
                    continue
                sub = db.execute(
                    select(MatterSubType).where(
                        MatterSubType.head_type_id == head.id,
                        MatterSubType.name == sub_name,
                    )
                ).scalar_one_or_none()
                if not sub:
                    sub_id = uuid.uuid4()
                    db.add(
                        MatterSubType(
                            id=sub_id,
                            head_type_id=head.id,
                            name=sub_name,
                            prefix=st.get("prefix"),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    db.flush()
                    sub = db.get(MatterSubType, sub_id)
                if not sub:
                    continue

                for menu_name in st.get("menus") or []:
                    mn = (menu_name or "").strip()
                    if not mn:
                        continue
                    exists = db.execute(
                        select(MatterSubTypeMenu).where(
                            MatterSubTypeMenu.sub_type_id == sub.id,
                            MatterSubTypeMenu.name == mn,
                        )
                    ).scalar_one_or_none()
                    if exists:
                        continue
                    db.add(
                        MatterSubTypeMenu(
                            id=uuid.uuid4(),
                            sub_type_id=sub.id,
                            name=mn,
                            created_at=now,
                            updated_at=now,
                        )
                    )

        db.commit()
    except Exception:
        db.rollback()
        raise

    log.info("Matter types synced from %s.", SEED_PATH)
    return True

"""Seed and sync matter head / sub types and sub-menus from Canary ``seed.json``.

Head matter type **names** are canonical (defined in ``matter_types_seed/seed.json``).
On each startup we **merge** any missing heads, sub-types, and menus from the seed
without removing firm-specific rows. Admins cannot create or rename head types via API;
they may only hide heads the firm does not use.

``default_sub_menus`` in the seed lists sub-menus applied to every sub-type (existing
and new from seed). Future sub-menus are opt-in via admin or an updated seed list.
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

# Fallback when seed.json has no ``default_sub_menus`` (current product sub-menus only).
CANONICAL_DEFAULT_SUB_MENUS = ("Events", "Finance", "Property", "Tasks")


def default_sub_menu_names_from_seed(raw: dict) -> list[str]:
    names = raw.get("default_sub_menus")
    if isinstance(names, list) and names:
        out = [(str(n) or "").strip() for n in names]
        return [n for n in out if n]
    return list(CANONICAL_DEFAULT_SUB_MENUS)


def load_default_sub_menu_names() -> list[str]:
    if not SEED_PATH.is_file():
        return list(CANONICAL_DEFAULT_SUB_MENUS)
    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return default_sub_menu_names_from_seed(raw)


def ensure_sub_type_menus(
    db: Session,
    sub: MatterSubType,
    menu_names: list[str],
    *,
    now: datetime,
) -> None:
    for menu_name in menu_names:
        mn = (menu_name or "").strip()
        if not mn:
            continue
        exists = db.execute(
            select(MatterSubTypeMenu.id).where(
                MatterSubTypeMenu.sub_type_id == sub.id,
                MatterSubTypeMenu.name == mn,
            ).limit(1)
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
    db.flush()


def dedupe_sub_type_menus(db: Session) -> None:
    """Remove duplicate menu names on the same sub-type (keep oldest row)."""
    rows = db.execute(
        select(MatterSubTypeMenu).order_by(MatterSubTypeMenu.sub_type_id, MatterSubTypeMenu.name, MatterSubTypeMenu.created_at)
    ).scalars().all()
    seen: set[tuple[uuid.UUID, str]] = set()
    for row in rows:
        key = (row.sub_type_id, row.name)
        if key in seen:
            db.delete(row)
        else:
            seen.add(key)
    db.flush()


def ensure_all_sub_types_have_default_menus(db: Session, menu_names: list[str], *, now: datetime) -> None:
    subs = db.execute(select(MatterSubType)).scalars().all()
    for sub in subs:
        ensure_sub_type_menus(db, sub, menu_names, now=now)


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

    default_menus = default_sub_menu_names_from_seed(raw)
    now = datetime.now(timezone.utc)
    try:
        dedupe_sub_type_menus(db)

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

                explicit = st.get("menus")
                menu_names = default_menus
                if isinstance(explicit, list) and explicit:
                    menu_names = [(str(n) or "").strip() for n in explicit if (str(n) or "").strip()]
                ensure_sub_type_menus(db, sub, menu_names, now=now)

        ensure_all_sub_types_have_default_menus(db, default_menus, now=now)
        dedupe_sub_type_menus(db)

        db.commit()
    except Exception:
        db.rollback()
        raise

    log.info("Matter types synced from %s.", SEED_PATH)
    return True

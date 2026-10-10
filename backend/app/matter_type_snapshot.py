"""Detach-safe matter type name snapshots on ``case``.

Live FKs (``matter_head_type_id`` / ``matter_sub_type_id``) point into the firm
catalogue and are cleared on detach. Stable **names** persist on the case so a
later attach can restore FKs by matching the firm catalogue.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, MatterHeadType, MatterSubType

log = logging.getLogger(__name__)


def sync_case_matter_type_snapshot(case: Case, db: Session) -> None:
    """Update name snapshots from the case's current live matter-type FKs.

    When FKs are cleared intentionally (Admin clears type), snapshots are cleared
    too. Detach should call ``capture_snapshots_before_unlink`` first so names
    survive FK nulling.
    """
    if case.matter_sub_type_id:
        sub = db.get(MatterSubType, case.matter_sub_type_id)
        if sub is None:
            return
        head = db.get(MatterHeadType, sub.head_type_id)
        case.matter_sub_type_name = sub.name
        case.matter_head_type_name = head.name if head else case.matter_head_type_name
        return
    if case.matter_head_type_id:
        head = db.get(MatterHeadType, case.matter_head_type_id)
        case.matter_head_type_name = head.name if head else None
        case.matter_sub_type_name = None
        return
    case.matter_head_type_name = None
    case.matter_sub_type_name = None


def capture_snapshots_before_unlink(db: Session) -> int:
    """Ensure every typed case has name snapshots before FKs are nulled (detach)."""
    cases = list(
        db.execute(
            select(Case).where(
                (Case.matter_head_type_id.is_not(None)) | (Case.matter_sub_type_id.is_not(None))
            )
        ).scalars()
    )
    n = 0
    for case in cases:
        before = (case.matter_head_type_name, case.matter_sub_type_name)
        sync_case_matter_type_snapshot(case, db)
        if (case.matter_head_type_name, case.matter_sub_type_name) != before or (
            case.matter_head_type_name or case.matter_sub_type_name
        ):
            db.add(case)
            n += 1
    if n:
        db.flush()
    return n


def restore_case_matter_types_from_snapshots(db: Session) -> int:
    """Restore live FKs from name snapshots where catalogue rows exist.

    Matching is by exact head name + sub name (case-insensitive trim). Cases
    with no matching catalogue row are left untyped (snapshot kept for later).
    """
    heads = {
        (h.name or "").strip().lower(): h
        for h in db.execute(select(MatterHeadType)).scalars()
    }
    if not heads:
        return 0

    subs_by_head: dict[str, dict[str, MatterSubType]] = {}
    for s in db.execute(select(MatterSubType)).scalars():
        head = db.get(MatterHeadType, s.head_type_id)
        if head is None:
            continue
        key = (head.name or "").strip().lower()
        subs_by_head.setdefault(key, {})[(s.name or "").strip().lower()] = s

    cases = list(
        db.execute(
            select(Case).where(
                (Case.matter_head_type_name.is_not(None)) | (Case.matter_sub_type_name.is_not(None))
            )
        ).scalars()
    )
    restored = 0
    for case in cases:
        head_key = (case.matter_head_type_name or "").strip().lower()
        sub_key = (case.matter_sub_type_name or "").strip().lower()
        head = heads.get(head_key) if head_key else None
        sub = None
        if head is not None and sub_key:
            sub = subs_by_head.get(head_key, {}).get(sub_key)
        elif sub_key and not head_key:
            # Sub name only: unique match across heads
            matches = [
                s
                for by_sub in subs_by_head.values()
                for name, s in by_sub.items()
                if name == sub_key
            ]
            if len(matches) == 1:
                sub = matches[0]
                head = db.get(MatterHeadType, sub.head_type_id)

        new_head_id = head.id if head else None
        new_sub_id = sub.id if sub else None
        if new_head_id is None and new_sub_id is None:
            continue
        if case.matter_head_type_id == new_head_id and case.matter_sub_type_id == new_sub_id:
            continue
        case.matter_head_type_id = new_head_id
        case.matter_sub_type_id = new_sub_id
        # Keep snapshots authoritative labels
        if head is not None:
            case.matter_head_type_name = head.name
        if sub is not None:
            case.matter_sub_type_name = sub.name
        db.add(case)
        restored += 1

    if restored:
        db.commit()
        log.info("Restored matter type FKs on %s case(s) from name snapshots.", restored)
    return restored

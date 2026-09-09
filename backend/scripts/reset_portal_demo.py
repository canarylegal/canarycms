#!/usr/bin/env python3
"""Reset portal demo pending items on matter 000002 (Sam Thomas), then re-seed.

Voids/supersedes leftover pending quotes, forms, and Canary Sign for that
contact on that matter, then re-runs seed_case_000002_portal_demo ensure logic.

  docker compose exec -e I_CONFIRM_CANARY_SEED=yes backend \\
    python scripts/reset_portal_demo.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from sqlalchemy import select

from app.canary_sign_service import list_pending_for_contact, void_signing_request
from app.db import SessionLocal
from app.models import (
    Case,
    ContactPortalAccess,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
)
from app.portal_form_service import void_submission
from app.portal_service import portal_access_is_active

import seed_case_000002_portal_demo as seed


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clear_pending(db, *, case: Case, contact, actor: User) -> dict[str, int]:
    """Void/supersede pending portal items for this contact on this matter."""
    now = _utcnow()
    counts = {"quotes": 0, "forms": 0, "signs": 0}

    quotes = (
        db.execute(
            select(QuotePortalDelivery).where(
                QuotePortalDelivery.case_id == case.id,
                QuotePortalDelivery.contact_id == contact.id,
                QuotePortalDelivery.status == QuotePortalDeliveryStatus.pending,
            )
        )
        .scalars()
        .all()
    )
    for row in quotes:
        # Same field updates as quote_portal_service.supersede_pending_quote_deliveries
        row.status = QuotePortalDeliveryStatus.superseded
        row.responded_at = now
        db.add(row)
        counts["quotes"] += 1
        print(f"  ~ superseded quote {row.id}")

    forms = (
        db.execute(
            select(PortalFormSubmission).where(
                PortalFormSubmission.case_id == case.id,
                PortalFormSubmission.contact_id == contact.id,
                PortalFormSubmission.status == PortalFormSubmissionStatus.pending,
            )
        )
        .scalars()
        .all()
    )
    for row in forms:
        void_submission(db, submission=row, actor=actor)
        counts["forms"] += 1
        print(f"  ~ voided form {row.id}")

    db.flush()

    for req, _recip in list_pending_for_contact(db, contact.id):
        if req.case_id != case.id:
            continue
        void_signing_request(db, req=req, actor=actor, reason="Portal demo reset")
        counts["signs"] += 1
        print(f"  ~ voided Canary Sign {req.id}")

    return counts


def main() -> None:
    if os.getenv("I_CONFIRM_CANARY_SEED", "").strip().lower() not in ("1", "true", "yes"):
        print("Set I_CONFIRM_CANARY_SEED=yes to run.", file=sys.stderr)
        sys.exit(1)

    case_number = os.getenv("CASE_NUMBER", seed.CASE_NUMBER).strip().zfill(6)
    counts = {"quotes": 0, "forms": 0, "signs": 0}

    db = SessionLocal()
    try:
        case = db.execute(select(Case).where(Case.case_number == case_number)).scalar_one_or_none()
        if case is None:
            raise RuntimeError(f"Case {case_number} not found")

        actor = db.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.created_at.asc())
        ).scalars().first()
        if actor is None:
            raise RuntimeError("No active user")

        contact = seed._find_contact(db, case.id)
        access = db.execute(
            select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
        ).scalar_one_or_none()
        if access is None or not portal_access_is_active(access):
            raise RuntimeError(
                f"{contact.name} does not have active portal access — grant it in the UI first"
            )

        print(f"Resetting portal demo on {case_number} for {contact.name}…")
        counts = _clear_pending(db, case=case, contact=contact, actor=actor)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # Re-run the same ensure path as seed (own session / confirm env already set).
    seed.main()

    print(
        f"Summary: superseded {counts['quotes']} quote(s), "
        f"voided {counts['forms']} form(s), voided {counts['signs']} Canary Sign(s); re-seeded."
    )


if __name__ == "__main__":
    main()

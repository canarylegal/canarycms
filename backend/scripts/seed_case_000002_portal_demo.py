#!/usr/bin/env python3
"""Seed portal demo content on matter 000002 for Sam Thomas.

Creates (idempotent-ish):
  - Shared folder grant with a couple of documents
  - Pending portal quote
  - Pending portal form
  - Pending Canary Sign (Sam only)

  docker compose exec -e I_CONFIRM_CANARY_SEED=yes backend \\
    python scripts/seed_case_000002_portal_demo.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from sqlalchemy import select

from app.canary_sign_service import list_pending_for_contact, send_signing_request
from app.db import SessionLocal
from app.file_storage import case_file_paths, ensure_files_root, sanitize_folder_path
from app.models import (
    CanarySignOrderMode,
    Case,
    CaseContact,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    File as DbFile,
    FileCategory,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
    PortalFormTemplate,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
)
from app.portal_form_service import send_form_to_contact
from app.portal_service import portal_access_is_active
from app.quote_portal_service import send_quote_via_portal

CASE_NUMBER = os.getenv("CASE_NUMBER", "000002").strip().zfill(6)
SHARED_FOLDER = "Shared with client"
CONTACT_EMAIL_HINTS = ("sam.thomas@example.com",)
CONTACT_NAME_HINTS = ("sam thomas",)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _find_contact(db, case_id: uuid.UUID) -> Contact:
    rows = db.execute(
        select(Contact, CaseContact)
        .join(CaseContact, CaseContact.contact_id == Contact.id)
        .where(CaseContact.case_id == case_id)
    ).all()
    for contact, _cc in rows:
        email = (contact.email or "").strip().lower()
        name = (contact.name or "").strip().lower()
        if email in CONTACT_EMAIL_HINTS or name in CONTACT_NAME_HINTS:
            return contact
    raise RuntimeError("Sam Thomas contact not found on this matter")


def _ensure_shared_docs(db, *, case: Case, actor: User, contact: Contact) -> ContactPortalGrant:
    folder = sanitize_folder_path(SHARED_FOLDER)
    ensure_files_root()

    # Move a couple of existing non-system files into the shared folder when still at root.
    candidates = db.execute(
        select(DbFile)
        .where(
            DbFile.case_id == case.id,
            DbFile.category == FileCategory.case_document,
        )
        .order_by(DbFile.created_at.asc())
    ).scalars().all()
    moved = 0
    for row in candidates:
        if (row.folder_path or "").strip():
            continue
        name = (row.original_filename or "").lower()
        if name in {"scan.pdf", "000002.eml"} or (moved < 2 and "quote" not in name and "(signed)" not in name):
            row.folder_path = folder
            row.updated_at = _utcnow()
            db.add(row)
            moved += 1
        if moved >= 2:
            break

    # Ensure at least one demo file exists in the folder.
    in_folder = db.execute(
        select(DbFile.id).where(
            DbFile.case_id == case.id,
            DbFile.folder_path == folder,
            DbFile.category == FileCategory.case_document,
        ).limit(1)
    ).scalar_one_or_none()
    if in_folder is None:
        file_id = uuid.uuid4()
        paths = case_file_paths(
            case_id=case.id,
            file_id=file_id,
            original_filename="Welcome pack.pdf",
            folder_path=folder,
        )
        paths.abs_path.parent.mkdir(parents=True, exist_ok=True)
        import pikepdf
        from io import BytesIO

        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = BytesIO()
        pdf.save(buf)
        paths.abs_path.write_bytes(buf.getvalue())
        db.add(
            DbFile(
                id=file_id,
                case_id=case.id,
                owner_id=actor.id,
                category=FileCategory.case_document,
                storage_path=paths.rel_path,
                folder_path=folder,
                is_pinned=False,
                original_filename="Welcome pack.pdf",
                mime_type="application/pdf",
                size_bytes=paths.abs_path.stat().st_size,
                version=1,
                checksum=None,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        print(f"  + created Welcome pack.pdf in {folder}/")

    grant = db.execute(
        select(ContactPortalGrant).where(
            ContactPortalGrant.case_id == case.id,
            ContactPortalGrant.contact_id == contact.id,
            ContactPortalGrant.folder_path == folder,
        )
    ).scalar_one_or_none()
    if grant is None:
        grant = ContactPortalGrant(
            id=uuid.uuid4(),
            contact_id=contact.id,
            case_id=case.id,
            folder_path=folder,
            label=None,
            can_download=True,
            can_upload=True,
            created_by_user_id=actor.id,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(grant)
        db.flush()
        print(f"  + folder grant → {folder}/")
    else:
        if (grant.label or "").strip():
            grant.label = None
            grant.updated_at = _utcnow()
            print(f"  ~ cleared stale grant label → {folder}/")
        else:
            print(f"  = folder grant already exists → {folder}/")
    return grant


def _ensure_quote(db, *, case: Case, actor: User, contact: Contact) -> None:
    pending = db.execute(
        select(QuotePortalDelivery).where(
            QuotePortalDelivery.case_id == case.id,
            QuotePortalDelivery.contact_id == contact.id,
            QuotePortalDelivery.status == QuotePortalDeliveryStatus.pending,
        )
    ).scalar_one_or_none()
    if pending:
        print("  = pending quote already exists")
        return

    quote_file = db.execute(
        select(DbFile)
        .where(
            DbFile.case_id == case.id,
            DbFile.category == FileCategory.case_document,
            DbFile.original_filename.ilike("%quote%"),
        )
        .order_by(DbFile.created_at.desc())
    ).scalars().first()
    if quote_file is None:
        print("  ! no quote file found — skipped quote seed")
        return

    # Demo seed: allow send even if the editor left a compose-pending flag.
    if getattr(quote_file, "oo_compose_pending", False):
        quote_file.oo_compose_pending = False
        quote_file.updated_at = _utcnow()
        db.add(quote_file)
        db.flush()

    delivery, email_sent, skip, _pdf = send_quote_via_portal(
        db,
        case_id=case.id,
        file_id=quote_file.id,
        contact_id=contact.id,
        actor_user_id=actor.id,
    )
    print(
        f"  + pending quote {delivery.id} ({quote_file.original_filename})"
        f" email_sent={email_sent} skip={skip}"
    )


def _ensure_form(db, *, case: Case, actor: User, contact: Contact) -> None:
    pending = db.execute(
        select(PortalFormSubmission).where(
            PortalFormSubmission.case_id == case.id,
            PortalFormSubmission.contact_id == contact.id,
            PortalFormSubmission.status == PortalFormSubmissionStatus.pending,
        )
    ).scalar_one_or_none()
    if pending:
        print("  = pending form already exists")
        return

    template = db.execute(
        select(PortalFormTemplate).where(PortalFormTemplate.reference == "general_information")
    ).scalar_one_or_none()
    if template is None:
        template = db.execute(select(PortalFormTemplate).order_by(PortalFormTemplate.name.asc())).scalars().first()
    if template is None:
        print("  ! no portal form templates — skipped form seed")
        return

    submission, email_sent, skip = send_form_to_contact(
        db,
        case_id=case.id,
        template_id=template.id,
        contact_id=contact.id,
        actor=actor,
    )
    print(
        f"  + pending form {submission.id} ({template.name})"
        f" email_sent={email_sent} skip={skip}"
    )


def _ensure_canary_sign(db, *, case: Case, actor: User, contact: Contact, case_contact_id: uuid.UUID) -> None:
    pending = list_pending_for_contact(db, contact.id)
    if any(req.case_id == case.id for req, _recip in pending):
        print("  = pending Canary Sign already exists for Sam")
        return

    from app.models import CanarySignRequest, CanarySignStatus

    busy_sources = {
        r.source_file_id
        for r in db.execute(
            select(CanarySignRequest).where(
                CanarySignRequest.case_id == case.id,
                CanarySignRequest.status == CanarySignStatus.pending,
            )
        ).scalars().all()
        if r.source_file_id
    }

    pdf = None
    for row in db.execute(
        select(DbFile)
        .where(
            DbFile.case_id == case.id,
            DbFile.category == FileCategory.case_document,
            DbFile.mime_type == "application/pdf",
        )
        .order_by(DbFile.created_at.asc())
    ).scalars().all():
        name = (row.original_filename or "").lower()
        if "(signed)" in name or "certificate" in name:
            continue
        if row.id in busy_sources:
            continue
        pdf = row
        break

    if pdf is None:
        print("  ! no free PDF for Canary Sign — skipped")
        return

    email = (contact.email or "").strip()
    if not email:
        print("  ! Sam has no email — skipped Canary Sign")
        return

    req = send_signing_request(
        db,
        case_id=case.id,
        actor=actor,
        source_file_id=pdf.id,
        subject=f"Please sign: {pdf.original_filename}",
        recipient_specs=[
            {
                "name": contact.name,
                "email": email,
                "routing_order": 1,
                "case_contact_id": str(case_contact_id),
                "contact_id": str(contact.id),
            }
        ],
        order_mode=CanarySignOrderMode.parallel,
        expires_in_days=14,
        fields_specs=[
            {
                "field_type": "signature",
                "routing_order": 1,
                "label": "Signature",
                "required": True,
                "sort_order": 0,
                "page": 1,
                "x_pct": 15,
                "y_pct": 70,
                "w_pct": 35,
                "h_pct": 10,
            },
            {
                "field_type": "date",
                "routing_order": 1,
                "label": "Date",
                "required": True,
                "sort_order": 1,
                "page": 1,
                "x_pct": 55,
                "y_pct": 70,
                "w_pct": 25,
                "h_pct": 6,
            },
        ],
        retain_fillable_form=False,
    )
    print(f"  + pending Canary Sign {req.id} on {pdf.original_filename}")


def main() -> None:
    if os.getenv("I_CONFIRM_CANARY_SEED", "").strip().lower() not in ("1", "true", "yes"):
        print("Set I_CONFIRM_CANARY_SEED=yes to run.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        case = db.execute(select(Case).where(Case.case_number == CASE_NUMBER)).scalar_one_or_none()
        if case is None:
            raise RuntimeError(f"Case {CASE_NUMBER} not found")
        if not case.portal_enabled:
            case.portal_enabled = True
            db.add(case)
            print(f"  + enabled portal on matter {CASE_NUMBER}")

        actor = db.execute(select(User).where(User.is_active.is_(True)).order_by(User.created_at.asc())).scalars().first()
        if actor is None:
            raise RuntimeError("No active user")

        contact = _find_contact(db, case.id)
        access = db.execute(
            select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
        ).scalar_one_or_none()
        if access is None or not portal_access_is_active(access):
            raise RuntimeError(
                f"{contact.name} does not have active portal access — grant it in the UI first"
            )

        cc = db.execute(
            select(CaseContact).where(
                CaseContact.case_id == case.id,
                CaseContact.contact_id == contact.id,
            )
        ).scalar_one()

        print(f"Seeding portal demo on {CASE_NUMBER} for {contact.name}…")
        _ensure_shared_docs(db, case=case, actor=actor, contact=contact)
        _ensure_quote(db, case=case, actor=actor, contact=contact)
        _ensure_form(db, case=case, actor=actor, contact=contact)
        _ensure_canary_sign(db, case=case, actor=actor, contact=contact, case_contact_id=cc.id)
        db.commit()
        print("Done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

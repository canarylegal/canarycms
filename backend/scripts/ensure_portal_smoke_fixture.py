#!/usr/bin/env python3
"""Ensure matter 000002 + Sam Thomas exist for portal smoke tests.

Idempotent. Safe on a populated demo DB (reuses existing rows).

  docker compose exec backend python scripts/ensure_portal_smoke_fixture.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

import pikepdf
from sqlalchemy import select

from app.db import SessionLocal
from app.file_storage import case_file_paths, ensure_files_root, sanitize_folder_path
from app.models import (
    Case,
    CaseContact,
    CaseReferenceCounter,
    CaseStatus,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    ContactType,
    File as DbFile,
    FileCategory,
    MatterHeadType,
    MatterSubType,
    PortalFormFieldType,
    PortalFormTemplate,
    PortalFormTemplateField,
    User,
    UserRole,
)
from app.portal_service import generate_access_code, store_portal_access_code
from app.security import hash_password

CASE_NUMBER = os.getenv("CASE_NUMBER", "000002").strip().zfill(6)
CONTACT_EMAIL = "sam.thomas@example.com"
CONTACT_NAME = "Sam Thomas"
SHARED_FOLDER = "Shared with client"
STAFF_EMAIL = os.getenv("PORTAL_SMOKE_STAFF_EMAIL", "colin@mcwilliamslegal.co.uk").strip().lower()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _valid_pdf() -> bytes:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _ensure_staff(db) -> User:
    user = db.execute(select(User).where(User.email == STAFF_EMAIL)).scalar_one_or_none()
    if user is None:
        user = db.execute(
            select(User).where(User.role == UserRole.admin, User.is_active.is_(True)).order_by(User.created_at.asc())
        ).scalars().first()
    if user is not None:
        return user

    now = _utcnow()
    # Unique initials for empty DBs (CI).
    initials = "SMK"
    clash = db.execute(select(User).where(User.initials == initials)).scalar_one_or_none()
    if clash is not None:
        initials = "S" + uuid.uuid4().hex[:3].upper()
    user = User(
        id=uuid.uuid4(),
        email=STAFF_EMAIL,
        password_hash=hash_password(os.getenv("PORTAL_SMOKE_STAFF_PASSWORD", "PortalSmoke!ChangeMe")),
        display_name="Portal Smoke Admin",
        initials=initials,
        role=UserRole.admin,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    print(f"  + created staff admin {user.email}")
    return user


def _matter_types(db) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    sub = db.execute(
        select(MatterSubType)
        .join(MatterHeadType, MatterSubType.head_type_id == MatterHeadType.id)
        .where(MatterHeadType.name == "Conveyancing, Residential", MatterSubType.name == "Purchase")
    ).scalar_one_or_none()
    if sub is None:
        sub = db.execute(select(MatterSubType).order_by(MatterSubType.name.asc())).scalars().first()
    if sub is None:
        return None, None
    return sub.head_type_id, sub.id


def _ensure_case(db, staff: User) -> Case:
    case = db.execute(select(Case).where(Case.case_number == CASE_NUMBER)).scalar_one_or_none()
    if case is not None:
        if not case.portal_enabled:
            case.portal_enabled = True
            case.updated_at = _utcnow()
            db.add(case)
            print("  = enabled portal on existing matter")
        return case

    head_id, sub_id = _matter_types(db)
    now = _utcnow()
    case = Case(
        id=uuid.uuid4(),
        case_number=CASE_NUMBER,
        title="Portal smoke fixture matter",
        client_name=CONTACT_NAME,
        fee_earner_user_id=staff.id,
        created_by=staff.id,
        status=CaseStatus.open,
        portal_enabled=True,
        matter_head_type_id=head_id,
        matter_sub_type_id=sub_id,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()

    counter = db.execute(select(CaseReferenceCounter).where(CaseReferenceCounter.id == 1)).scalar_one_or_none()
    if counter is None:
        db.add(CaseReferenceCounter(id=1, next_value=3))
    else:
        try:
            n = int(CASE_NUMBER) + 1
        except ValueError:
            n = 3
        if int(counter.next_value or 1) < n:
            counter.next_value = n
            db.add(counter)
    print(f"  + created matter {CASE_NUMBER}")
    return case


def _ensure_contact(db, case: Case, staff: User) -> tuple[Contact, CaseContact, ContactPortalAccess]:
    contact = db.execute(select(Contact).where(Contact.email == CONTACT_EMAIL)).scalar_one_or_none()
    now = _utcnow()
    if contact is None:
        contact = Contact(
            id=uuid.uuid4(),
            type=ContactType.person,
            name=CONTACT_NAME,
            email=CONTACT_EMAIL,
            first_name="Sam",
            last_name="Thomas",
            created_at=now,
            updated_at=now,
        )
        db.add(contact)
        db.flush()
        print(f"  + created contact {CONTACT_EMAIL}")

    cc = db.execute(
        select(CaseContact).where(CaseContact.case_id == case.id, CaseContact.contact_id == contact.id)
    ).scalar_one_or_none()
    if cc is None:
        cc = CaseContact(
            id=uuid.uuid4(),
            case_id=case.id,
            contact_id=contact.id,
            is_linked_to_master=True,
            type=ContactType.person,
            name=CONTACT_NAME,
            email=CONTACT_EMAIL,
            first_name="Sam",
            last_name="Thomas",
            matter_contact_type="client",
            created_at=now,
            updated_at=now,
        )
        db.add(cc)
        db.flush()
        print("  + linked Sam to matter")

    access = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    ).scalar_one_or_none()
    if access is None:
        code = generate_access_code()
        access = ContactPortalAccess(
            id=uuid.uuid4(),
            contact_id=contact.id,
            code_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
            enabled=True,
            created_by_user_id=staff.id,
            created_at=now,
            updated_at=now,
        )
        db.add(access)
        db.flush()
        store_portal_access_code(access, code)
        db.add(access)
        print("  + created portal access")
    elif not access.enabled:
        access.enabled = True
        access.updated_at = now
        db.add(access)
        print("  = re-enabled portal access")
    return contact, cc, access


def _ensure_shared_docs(db, *, case: Case, staff: User, contact: Contact) -> None:
    ensure_files_root()
    folder = sanitize_folder_path(SHARED_FOLDER)
    grant = db.execute(
        select(ContactPortalGrant).where(
            ContactPortalGrant.case_id == case.id,
            ContactPortalGrant.contact_id == contact.id,
            ContactPortalGrant.folder_path == folder,
        )
    ).scalar_one_or_none()
    now = _utcnow()
    if grant is None:
        grant = ContactPortalGrant(
            id=uuid.uuid4(),
            contact_id=contact.id,
            case_id=case.id,
            folder_path=folder,
            label=SHARED_FOLDER,
            can_download=True,
            can_upload=True,
            created_by_user_id=staff.id,
            created_at=now,
            updated_at=now,
        )
        db.add(grant)
        db.flush()
        print(f"  + shared folder grant '{SHARED_FOLDER}'")

    pdf_bytes = _valid_pdf()
    for name in ("Client quote.pdf", "Agreement to sign.pdf"):
        existing = db.execute(
            select(DbFile).where(
                DbFile.case_id == case.id,
                DbFile.original_filename == name,
                DbFile.category == FileCategory.case_document,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        file_id = uuid.uuid4()
        paths = case_file_paths(
            case_id=case.id,
            file_id=file_id,
            original_filename=name,
            folder_path=folder if name == "Agreement to sign.pdf" else "",
        )
        paths.abs_path.parent.mkdir(parents=True, exist_ok=True)
        paths.abs_path.write_bytes(pdf_bytes)
        row = DbFile(
            id=file_id,
            case_id=case.id,
            owner_id=staff.id,
            category=FileCategory.case_document,
            storage_path=paths.rel_path,
            folder_path=paths.folder_path,
            original_filename=name,
            mime_type="application/pdf",
            size_bytes=len(pdf_bytes),
            version=1,
            oo_compose_pending=False,
            is_portal_quote=False,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        print(f"  + file {name}")
    db.flush()


def _ensure_form_template(db, staff: User) -> None:
    tmpl = db.execute(
        select(PortalFormTemplate).where(PortalFormTemplate.reference == "general_information")
    ).scalar_one_or_none()
    if tmpl is None:
        tmpl = db.execute(select(PortalFormTemplate).order_by(PortalFormTemplate.name.asc())).scalars().first()
    if tmpl is not None:
        return
    now = _utcnow()
    tmpl = PortalFormTemplate(
        id=uuid.uuid4(),
        name="General information",
        reference="general_information",
        description="Portal smoke fixture template",
        matter_head_type_id=None,
        matter_sub_type_id=None,
        owner_id=staff.id,
        created_at=now,
        updated_at=now,
    )
    db.add(tmpl)
    db.flush()
    db.add(
        PortalFormTemplateField(
            id=uuid.uuid4(),
            template_id=tmpl.id,
            field_key="full_name",
            label="Full name",
            field_type=PortalFormFieldType.text,
            required=True,
            sort_order=10,
            select_options=[],
        )
    )
    db.add(
        PortalFormTemplateField(
            id=uuid.uuid4(),
            template_id=tmpl.id,
            field_key="notes",
            label="Notes",
            field_type=PortalFormFieldType.textarea,
            required=False,
            sort_order=20,
            select_options=[],
        )
    )
    print("  + portal form template general_information")


def main() -> int:
    print(f"Ensuring portal smoke fixture for matter {CASE_NUMBER}")
    db = SessionLocal()
    try:
        staff = _ensure_staff(db)
        case = _ensure_case(db, staff)
        contact, _cc, _access = _ensure_contact(db, case, staff)
        _ensure_shared_docs(db, case=case, staff=staff, contact=contact)
        _ensure_form_template(db, staff)
        db.commit()
        print("Fixture ready.")
        return 0
    except Exception as e:
        db.rollback()
        print(f"FAILED: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create 20 sample matters with one random file each (.txt, .pdf, .eml, ONLYOFFICE types).

Requires env I_CONFIRM_CANARY_SEED=yes and a migrated DB (fee earner required on cases).

Run via Docker (recommended — uses the backend image deps and DB):

  docker compose exec backend alembic upgrade head
  docker compose run --rm -e I_CONFIRM_CANARY_SEED=yes \\
    -v ./backend:/app -v ./data/files:/data/files \\
    backend python scripts/seed_sample_cases_and_files.py

Or with dev bind-mount (``docker-compose.dev.yml``), after ``docker compose up``:

  docker compose exec -e I_CONFIRM_CANARY_SEED=yes backend python scripts/seed_sample_cases_and_files.py

Rebuild the backend image if you are not using the dev overlay and the script is missing in the container:

  docker compose build backend && docker compose up -d backend

Local venv (only if dependencies from requirements.txt are installed):

  cd backend && I_CONFIRM_CANARY_SEED=yes python scripts/seed_sample_cases_and_files.py
"""

from __future__ import annotations

import os
import random
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from sqlalchemy import select

from app.case_client_sync import sync_case_client_name
from app.case_matter_description import build_matter_description, random_uk_address_lines
from app.db import SessionLocal
from app.docx_util import write_blank_docx
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root
from app.matter_contact_constants import CLIENT_SLUG
from app.models import (
    Case,
    CaseContact,
    CaseReferenceCounter,
    CaseStatus,
    Contact,
    ContactType,
    File as DbFile,
    FileCategory,
    MatterSubType,
    User,
)

SAMPLE_COUNT = 20

FIRST_NAMES = (
    "Alex",
    "Jordan",
    "Sam",
    "Taylor",
    "Morgan",
    "Riley",
    "Casey",
    "Jamie",
    "Robin",
    "Avery",
)
LAST_NAMES = (
    "Smith",
    "Jones",
    "Williams",
    "Brown",
    "Davies",
    "Evans",
    "Wilson",
    "Taylor",
    "Thomas",
    "Roberts",
)
FILE_SPECS: list[tuple[str, str]] = [
    ("notes.txt", "text/plain"),
    ("scan.pdf", "application/pdf"),
    ("inbound.eml", "message/rfc822"),
    ("letter.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("figures.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("slides.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ("memo.odt", "application/vnd.oasis.opendocument.text"),
    ("brief.rtf", "application/rtf"),
    ("correspondence.txt", "text/plain"),
    ("contract.pdf", "application/pdf"),
    ("reply.eml", "message/rfc822"),
    ("draft.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("budget.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("hearing-notes.txt", "text/plain"),
    ("exhibit.pdf", "application/pdf"),
    ("client-email.eml", "message/rfc822"),
    ("schedule.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("outline.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ("summary.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("archive.rtf", "application/rtf"),
]


def _minimal_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _minimal_eml(subject: str, body: str) -> bytes:
    mid = f"<{uuid.uuid4()}@canary-seed.local>"
    hdr = (
        f"From: sender@example.com\r\n"
        f"To: client@example.com\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: {mid}\r\n"
        f"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{body}\r\n"
    )
    return hdr.encode("utf-8")


def _minimal_rtf(text: str) -> bytes:
    safe = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return f"{{\\rtf1\\ansi {safe}}}".encode("utf-8")


def _minimal_ooxml_zip(content_types: str, part_path: str, part_xml: str) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr(part_path, part_xml)
    return buf.getvalue()


def _write_xlsx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from openpyxl import Workbook

        wb = Workbook()
        wb.active.title = "Sheet1"
        wb.active["A1"] = "Sample"
        wb.save(path)
        return
    except Exception:
        pass
    ct = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        "</Types>"
    )
    wb_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>'
        '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    path.write_bytes(_minimal_ooxml_zip(ct, "xl/workbook.xml", wb_xml))


def _write_pptx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ct = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        "</Types>"
    )
    pres = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'
    )
    path.write_bytes(_minimal_ooxml_zip(ct, "ppt/presentation.xml", pres))


def _write_odt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ct = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/content.xml" ContentType="application/vnd.oasis.opendocument.text"/>'
        "</Types>"
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:body><office:text><text:p>Sample ODT</text:p></office:text></office:body>"
        "</office:document-content>"
    )
    path.write_bytes(_minimal_ooxml_zip(ct, "content.xml", content))


def _materialize_file(path: Path, filename: str, mime: str, case_number: str) -> int:
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        path.write_text(f"Sample text for matter {case_number}.\n", encoding="utf-8")
    elif ext == ".pdf":
        path.write_bytes(_minimal_pdf())
    elif ext == ".eml":
        path.write_bytes(_minimal_eml(f"Matter {case_number}", f"Sample e-mail body for {case_number}."))
    elif ext == ".docx":
        write_blank_docx(path)
    elif ext == ".xlsx":
        _write_xlsx(path)
    elif ext == ".pptx":
        _write_pptx(path)
    elif ext == ".odt":
        _write_odt(path)
    elif ext == ".rtf":
        path.write_bytes(_minimal_rtf(f"Sample RTF for matter {case_number}"))
    else:
        path.write_bytes(b"sample")
    return path.stat().st_size


def _next_case_number(db) -> str:
    counter = db.get(CaseReferenceCounter, 1)
    if not counter:
        counter = CaseReferenceCounter(id=1, next_value=1)
        db.add(counter)
        db.flush()
    counter = db.execute(select(CaseReferenceCounter).where(CaseReferenceCounter.id == 1).with_for_update()).scalar_one()
    n = counter.next_value
    counter.next_value = n + 1
    return f"{n:06d}"


def main() -> None:
    if os.getenv("I_CONFIRM_CANARY_SEED", "").strip().lower() not in ("1", "true", "yes"):
        print("Set I_CONFIRM_CANARY_SEED=yes to run.", file=sys.stderr)
        sys.exit(1)

    ensure_files_root()
    db = SessionLocal()
    try:
        users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()
        if not users:
            print("No active users — create at least one user first.", file=sys.stderr)
            sys.exit(1)
        subs = db.execute(select(MatterSubType)).scalars().all()
        if not subs:
            print("No matter sub-types — run matter type seed first.", file=sys.stderr)
            sys.exit(1)
        creator = users[0]

        created_cases: list[Case] = []
        for i in range(SAMPLE_COUNT):
            fn = random.choice(FIRST_NAMES)
            ln = random.choice(LAST_NAMES)
            client_name = f"{fn} {ln}"
            sub = random.choice(subs)
            fee = random.choice(users)
            case_number = _next_case_number(db)
            description = build_matter_description(sub.prefix, random_uk_address_lines())[:300]
            case = Case(
                case_number=case_number,
                client_name=client_name,
                title=description,
                status=random.choice([CaseStatus.open, CaseStatus.quote]),
                practice_area=None,
                matter_sub_type_id=sub.id,
                matter_head_type_id=sub.head_type_id,
                fee_earner_user_id=fee.id,
                created_by=creator.id,
                is_locked=False,
            )
            db.add(case)
            db.flush()

            cc = CaseContact(
                case_id=case.id,
                contact_id=None,
                is_linked_to_master=False,
                type=ContactType.person,
                name=client_name,
                email=f"{fn.lower()}.{ln.lower()}@example.com",
                phone=None,
                first_name=fn,
                last_name=ln,
                matter_contact_type=CLIENT_SLUG,
            )
            db.add(cc)
            sync_case_client_name(db, case.id)  # flush inside sync sees the new contact
            created_cases.append(case)

            filename, mime = FILE_SPECS[i % len(FILE_SPECS)]
            file_id = uuid.uuid4()
            paths = case_file_paths(
                case_id=case.id,
                file_id=file_id,
                original_filename=filename,
                folder_path="",
            )
            size = _materialize_file(paths.abs_path, filename, mime, case_number)
            row = DbFile(
                id=file_id,
                case_id=case.id,
                owner_id=creator.id,
                category=FileCategory.case_document,
                storage_path=paths.rel_path,
                folder_path=paths.folder_path,
                original_filename=filename,
                mime_type=mime,
                size_bytes=size,
                is_pinned=False,
                oo_compose_pending=False,
            )
            db.add(row)

        db.commit()
        print(f"Created {len(created_cases)} cases with {len(created_cases)} files under {FILES_ROOT}")
        for c in created_cases:
            db.refresh(c)
            print(f"  {c.case_number} — {c.client_name or '(no client)'} — fee earner {c.fee_earner_user_id}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

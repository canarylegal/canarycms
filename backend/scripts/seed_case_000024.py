#!/usr/bin/env python3
"""Enrich a single existing matter with documents, contacts, tasks, events, and ledger data.

Default target: case 000024 (residential purchase).

  docker compose exec -e I_CONFIRM_CANARY_SEED=yes backend python scripts/seed_case_000024.py

Optional: CASE_NUMBER=000024
"""

from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from sqlalchemy import func, or_, select

from app.case_client_sync import sync_case_client_name
from app.db import SessionLocal
from app.file_storage import case_file_paths, ensure_files_root
from app.finance_service import get_finance
from app.ledger_service import post_transaction
from app.matter_contact_constants import CLIENT_SLUG, LAWYERS_SLUG
from app.models import (
    Case,
    CaseContact,
    CaseEvent,
    CaseTask,
    CaseTaskStatus,
    ContactType,
    File as DbFile,
    FileCategory,
    LedgerEntry,
    MatterSubTypeStandardTask,
    User,
    UserRole,
)
from app.schemas import LedgerPostCreate

import importlib.util

_sample_path = _ROOT / "scripts" / "seed_sample_cases_and_files.py"
_spec = importlib.util.spec_from_file_location("seed_sample_cases_and_files", _sample_path)
assert _spec and _spec.loader
_sample = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sample)
_materialize_file = _sample._materialize_file

CASE_NUMBER = os.getenv("CASE_NUMBER", "000024").strip().zfill(6)

DOCUMENTS: list[tuple[str, str, str]] = [
    ("Client care letter.pdf", "application/pdf", "Correspondence"),
    ("Terms of business - signed.pdf", "application/pdf", "Correspondence"),
    ("ID verification - passport.pdf", "application/pdf", "Client documents"),
    ("Proof of address - utility bill.pdf", "application/pdf", "Client documents"),
    ("Source of funds declaration.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Client documents"),
    ("Purchase questionnaire - completed.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Client documents"),
    ("TR1 - draft.pdf", "application/pdf", "Transfer"),
    ("Contract - draft.pdf", "application/pdf", "Contract"),
    ("Contract - engrossed.pdf", "application/pdf", "Contract"),
    ("Title register - official copy.pdf", "application/pdf", "Title"),
    ("Title plan - official copy.pdf", "application/pdf", "Title"),
    ("Local authority search.pdf", "application/pdf", "Searches"),
    ("Water and drainage search.pdf", "application/pdf", "Searches"),
    ("Environmental search.pdf", "application/pdf", "Searches"),
    ("Chancel repair liability search.pdf", "application/pdf", "Searches"),
    ("Coal mining search.pdf", "application/pdf", "Searches"),
    ("Planning search results.pdf", "application/pdf", "Searches"),
    ("Management pack - leasehold.pdf", "application/pdf", "Leasehold"),
    ("Service charge accounts.pdf", "application/pdf", "Leasehold"),
    ("Buildings insurance schedule.pdf", "application/pdf", "Insurance"),
    ("Mortgage offer - Halifax.pdf", "application/pdf", "Mortgage"),
    ("Mortgage valuation report.pdf", "application/pdf", "Mortgage"),
    ("Survey report - homebuyers.pdf", "application/pdf", "Survey"),
    ("Lender requirements checklist.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Mortgage"),
    ("SDLT calculation worksheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Tax"),
    ("Completion statement - draft.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Accounts"),
    ("Completion statement - final.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Accounts"),
    ("Redemption statement - existing lender.pdf", "application/pdf", "Mortgage"),
    ("Land Registry application AP1.pdf", "application/pdf", "Post-completion"),
    ("Transfer deed TR1 - signed.pdf", "application/pdf", "Transfer"),
    ("Report on title.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Title"),
    ("Email from estate agent.eml", "message/rfc822", "Correspondence"),
    ("Email from seller solicitor.eml", "message/rfc822", "Correspondence"),
    ("Email - mortgage offer received.eml", "message/rfc822", "Mortgage"),
    ("Searches invoice.pdf", "application/pdf", "Accounts"),
    ("Land Registry fees receipt.pdf", "application/pdf", "Accounts"),
    ("Bank transfer - deposit confirmation.pdf", "application/pdf", "Accounts"),
    ("Bank transfer - completion funds.pdf", "application/pdf", "Accounts"),
    ("Exchange checklist.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Exchange"),
    ("Completion checklist.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Completion"),
    ("Key release authorisation.pdf", "application/pdf", "Completion"),
    ("Post-completion SDLT receipt.pdf", "application/pdf", "Post-completion"),
    ("Land Registry completion confirmation.pdf", "application/pdf", "Post-completion"),
    ("Memo - chasing searches.txt", "text/plain", "Notes"),
    ("Memo - contract amendments.txt", "text/plain", "Notes"),
    ("Enquiries raised - draft.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Enquiries"),
    ("Enquiries replied - seller solicitor.pdf", "application/pdf", "Enquiries"),
    ("Fixtures and fittings form TA10.pdf", "application/pdf", "Protocol forms"),
    ("Property information form TA6.pdf", "application/pdf", "Protocol forms"),
    ("Final client report letter.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Correspondence"),
]

EXTRA_CONTACTS: list[tuple[str, ContactType, str, str | None, str | None]] = [
    (
        "Thompson & Co Solicitors LLP",
        ContactType.organisation,
        "lawyers",
        "conveyancing@thompsonco.example.com",
        "01244 555 010",
    ),
    (
        "Halifax",
        ContactType.organisation,
        "new-lender",
        "mortgages@halifax.example.com",
        None,
    ),
]

TASK_TITLES = (
    "Order property searches",
    "Raise pre-contract enquiries",
    "Review draft contract",
    "Chase mortgage offer",
    "Book survey with client",
    "Prepare report on title",
    "Obtain signed TR1",
    "Agree exchange date with all parties",
    "Prepare completion statement",
    "Submit SDLT return",
)

CALENDAR_EVENTS: list[tuple[str, int, bool, time | None]] = [
    ("Instruction received", -45, True, None),
    ("Searches ordered", -38, True, None),
    ("Draft contract received", -28, True, None),
    ("Mortgage offer received", -21, True, None),
    ("Survey appointment", -14, False, time(10, 30)),
    ("Exchange of contracts", -7, True, None),
    ("Completion", 14, True, None),
    ("SDLT payment deadline", 28, True, None),
    ("Post-completion filing", 35, True, None),
    ("Client handover call", 42, False, time(14, 0)),
]

LEDGER_CLIENT_RECEIPTS = (
    ("Client payment on account", "TT/{ref}"),
    ("Telegraphic transfer from client", "TT/{ref}"),
    ("Initial deposit received", "DEP/{ref}"),
    ("Completion funds received", "COMP/{ref}"),
)

LEDGER_OFFICE_DISBURSEMENTS = (
    ("Local authority search", "LAS/{ref}"),
    ("Water and drainage search", "WDS/{ref}"),
    ("Environmental search", "ENV/{ref}"),
    ("Land Registry official copy", "LR/{ref}"),
    ("AML identity check fee", "AML/{ref}"),
)

LEDGER_TRANSFERS = (
    ("Transfer to office — professional fees", "FEES/{ref}"),
    ("Transfer to office — completion fee", "COMP/{ref}"),
)


def _pick_poster(users: list[User]) -> User:
    for u in users:
        if u.role == UserRole.admin:
            return u
    return users[0]


def _standard_tasks_for_sub(db, sub_id: uuid.UUID) -> list[MatterSubTypeStandardTask]:
    return list(
        db.execute(
            select(MatterSubTypeStandardTask)
            .where(
                or_(
                    MatterSubTypeStandardTask.matter_sub_type_id == sub_id,
                    MatterSubTypeStandardTask.matter_sub_type_id.is_(None),
                )
            )
            .order_by(MatterSubTypeStandardTask.sort_order, MatterSubTypeStandardTask.title)
        )
        .scalars()
        .all()
    )


def _seed_files(db, *, case: Case, owner: User, target: int) -> int:
    existing = db.execute(
        select(func.count()).select_from(DbFile).where(DbFile.case_id == case.id)
    ).scalar_one()
    if existing >= target:
        print(f"  Skipping files — already {existing} on matter")
        return 0

    added = 0
    folders: dict[str, int] = {}
    for filename, mime, folder in DOCUMENTS[:target - existing]:
        file_id = uuid.uuid4()
        paths = case_file_paths(
            case_id=case.id,
            file_id=file_id,
            original_filename=filename,
            folder_path=folder,
        )
        size = _materialize_file(paths.abs_path, filename, mime, case.case_number)
        db.add(
            DbFile(
                id=file_id,
                case_id=case.id,
                owner_id=owner.id,
                category=FileCategory.case_document,
                storage_path=paths.rel_path,
                folder_path=paths.folder_path,
                original_filename=filename,
                mime_type=mime,
                size_bytes=size,
                is_pinned=folders.get(folder, 0) == 0 and folder in ("Contract", "Title"),
                oo_compose_pending=False,
            )
        )
        folders[folder] = folders.get(folder, 0) + 1
        added += 1
    return added


def _seed_contacts(db, *, case: Case, target: int) -> int:
    existing = db.execute(
        select(func.count()).select_from(CaseContact).where(CaseContact.case_id == case.id)
    ).scalar_one()
    if existing >= target:
        print(f"  Skipping contacts — already {existing} on matter")
        return 0

    added = 0
    for name, ctype, slug, email, phone in EXTRA_CONTACTS:
        if existing + added >= target:
            break
        db.add(
            CaseContact(
                case_id=case.id,
                contact_id=None,
                is_linked_to_master=False,
                type=ctype,
                name=name,
                email=email,
                phone=phone,
                matter_contact_type=slug,
            )
        )
        added += 1
    if added:
        sync_case_client_name(db, case.id)
    return added


def _seed_tasks(db, *, case: Case, creator: User, users: list[User], target: int) -> int:
    existing = db.execute(
        select(func.count()).select_from(CaseTask).where(CaseTask.case_id == case.id)
    ).scalar_one()
    if existing >= target:
        print(f"  Skipping tasks — already {existing} on matter")
        return 0

    standard = _standard_tasks_for_sub(db, case.matter_sub_type_id)
    std_by_title = {st.title: st.id for st in standard}
    now = datetime.now(timezone.utc)
    added = 0
    for i, title in enumerate(TASK_TITLES):
        if existing + added >= target:
            break
        status = CaseTaskStatus.open if i < 6 else random.choice((CaseTaskStatus.open, CaseTaskStatus.done))
        db.add(
            CaseTask(
                case_id=case.id,
                created_by_user_id=creator.id,
                title=title,
                description=random.choice(
                    (
                        None,
                        "Follow up with client if no response within 48 hours.",
                        "Coordinate with fee earner before chasing third party.",
                    )
                ),
                status=status,
                due_at=now + timedelta(days=random.randint(-7, 30)),
                standard_task_id=std_by_title.get(title),
                assigned_to_user_id=case.fee_earner_user_id or creator.id,
                priority=random.choice(("normal", "normal", "high")),
                is_private=False,
                created_at=now - timedelta(days=random.randint(5, 60)),
                updated_at=now - timedelta(days=random.randint(0, 14)),
            )
        )
        added += 1
    return added


def _seed_events(db, *, case: Case, target: int) -> int:
    existing = db.execute(
        select(func.count()).select_from(CaseEvent).where(CaseEvent.case_id == case.id)
    ).scalar_one()
    if existing >= target:
        print(f"  Skipping events — already {existing} on matter")
        return 0

    today = date.today()
    now = datetime.now(timezone.utc)
    added = 0
    for i, (name, day_offset, all_day, start_time) in enumerate(CALENDAR_EVENTS):
        if existing + added >= target:
            break
        db.add(
            CaseEvent(
                case_id=case.id,
                name=name,
                sort_order=i,
                event_date=today + timedelta(days=day_offset),
                event_all_day=all_day,
                event_start_time=start_time,
                track_in_calendar=True,
                created_at=now,
                updated_at=now,
            )
        )
        added += 1
    return added


def _post_ledger(
    db,
    *,
    case_id: uuid.UUID,
    poster: User,
    amount_pence: int,
    description: str,
    reference: str | None,
    client_direction: str | None = None,
    office_direction: str | None = None,
    posted_at: datetime,
    contact_label: str | None = None,
) -> None:
    result = post_transaction(
        case_id,
        LedgerPostCreate(
            description=description,
            reference=reference,
            amount_pence=amount_pence,
            client_direction=client_direction,
            office_direction=office_direction,
            contact_label=contact_label,
        ),
        poster,
        db,
    )
    legs = db.execute(select(LedgerEntry).where(LedgerEntry.pair_id == result.pair_id)).scalars().all()
    for leg in legs:
        leg.posted_at = posted_at


def _seed_ledger(db, *, case: Case, poster: User, client_name: str) -> int:
    ref = case.case_number
    now = datetime.now(timezone.utc)
    client_balance = 0
    count = 0

    for i, amount in enumerate((150_000, 250_000)):
        template = LEDGER_CLIENT_RECEIPTS[i]
        posted_at = now - timedelta(days=90 - i * 20)
        _post_ledger(
            db,
            case_id=case.id,
            poster=poster,
            amount_pence=amount,
            description=template[0],
            reference=template[1].format(ref=f"{ref}-{i + 1}"),
            client_direction="credit",
            posted_at=posted_at,
            contact_label=client_name,
        )
        client_balance += amount
        count += 1

    for i, amount in enumerate((4_500, 6_000, 3_500, 2_500, 7_500)):
        template = LEDGER_OFFICE_DISBURSEMENTS[i]
        _post_ledger(
            db,
            case_id=case.id,
            poster=poster,
            amount_pence=amount,
            description=template[0],
            reference=template[1].format(ref=f"{ref}-D{i + 1}"),
            office_direction="debit",
            posted_at=now - timedelta(days=60 - i * 5),
        )
        count += 1

    for i, amount in enumerate((35_000, 25_000)):
        if amount > client_balance:
            continue
        template = LEDGER_TRANSFERS[i]
        _post_ledger(
            db,
            case_id=case.id,
            poster=poster,
            amount_pence=amount,
            description=template[0],
            reference=template[1].format(ref=f"{ref}-T{i + 1}"),
            client_direction="debit",
            office_direction="credit",
            posted_at=now - timedelta(days=30 - i * 10),
            contact_label=client_name,
        )
        client_balance -= amount
        count += 1

    return count


def main() -> None:
    if os.getenv("I_CONFIRM_CANARY_SEED", "").strip().lower() not in ("1", "true", "yes"):
        print("Set I_CONFIRM_CANARY_SEED=yes to run.", file=sys.stderr)
        sys.exit(1)

    ensure_files_root()
    db = SessionLocal()
    try:
        case = db.execute(select(Case).where(Case.case_number == CASE_NUMBER)).scalar_one_or_none()
        if not case:
            print(f"Case {CASE_NUMBER} not found.", file=sys.stderr)
            sys.exit(1)

        users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()
        if not users:
            print("No active users.", file=sys.stderr)
            sys.exit(1)

        owner = _pick_poster(users)
        client_name = case.client_name or "Client"

        print(f"Seeding matter {case.case_number} — {client_name} — {case.title[:70]}")

        file_count = _seed_files(db, case=case, owner=owner, target=50)
        contact_count = _seed_contacts(db, case=case, target=3)
        task_count = _seed_tasks(db, case=case, creator=owner, users=users, target=10)
        event_count = _seed_events(db, case=case, target=10)

        get_finance(case.id, db)
        ledger_count = _seed_ledger(db, case=case, poster=owner, client_name=client_name)

        db.commit()
        print(
            f"Done: +{file_count} files, +{contact_count} contacts, +{task_count} tasks, "
            f"+{event_count} calendar events, +{ledger_count} ledger postings."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

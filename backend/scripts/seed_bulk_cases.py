#!/usr/bin/env python3
"""Create sample matters with tasks and ledger data (no documents).

Requires env I_CONFIRM_CANARY_SEED=yes and a migrated DB.

  docker compose exec -e I_CONFIRM_CANARY_SEED=yes backend python scripts/seed_bulk_cases.py

Optional: SEED_BULK_CASE_COUNT=100 (default 100).
"""

from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import or_, select

from app.case_client_sync import sync_case_client_name
from app.case_matter_description import build_matter_description, random_uk_address_lines
from app.db import SessionLocal
from app.finance_service import get_finance
from app.ledger_service import post_transaction
from app.matter_contact_constants import CLIENT_SLUG
from app.models import (
    Case,
    CaseContact,
    CaseReferenceCounter,
    CaseStatus,
    CaseTask,
    CaseTaskStatus,
    ContactType,
    MatterSubType,
    MatterSubTypeStandardTask,
    User,
    UserRole,
)
from app.schemas import LedgerPostCreate

SAMPLE_COUNT = int(os.getenv("SEED_BULK_CASE_COUNT", "100"))

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
    "Chris",
    "Drew",
    "Elliot",
    "Frankie",
    "Harper",
    "Jess",
    "Kim",
    "Leslie",
    "Pat",
    "Quinn",
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
    "Johnson",
    "Walker",
    "Wright",
    "Thompson",
    "White",
    "Edwards",
    "Green",
    "Hall",
    "Lewis",
    "Harris",
)

EXTRA_TASK_TITLES = (
    "Chase mortgage offer",
    "Review draft contract",
    "Send completion statement",
    "Obtain signed TR1",
    "Confirm exchange date with all parties",
    "Raise requisitions on title",
    "Check planning compliance certificate",
    "Request redemption figure",
    "Book completion slot with lender",
    "Send post-completion SDLT confirmation",
    "Review management pack",
    "Chase seller's solicitor for replies",
    "Prepare completion checklist",
    "Confirm buildings insurance on risk",
    "Arrange key collection",
    "Send initial letters to client",
    "Verify source of funds",
    "Order property searches",
    "Review leasehold information",
    "Draft report on title",
)

LEDGER_CLIENT_RECEIPTS = (
    ("Client payment on account", "TT/{ref}"),
    ("Telegraphic transfer from client", "TT/{ref}"),
    ("Initial deposit received", "DEP/{ref}"),
    ("Further client payment", "TT/{ref}"),
    ("Completion funds received", "COMP/{ref}"),
)

LEDGER_OFFICE_DISBURSEMENTS = (
    ("Land Registry official copy", "LR/{ref}"),
    ("Local authority search", "LAS/{ref}"),
    ("Water and drainage search", "WDS/{ref}"),
    ("Environmental search", "ENV/{ref}"),
    ("AML identity check fee", "AML/{ref}"),
    ("Bank transfer charge", "BANK/{ref}"),
)

LEDGER_TRANSFERS = (
    ("Transfer to office — professional fees", "FEES/{ref}"),
    ("Transfer to office — completion fee", "COMP/{ref}"),
    ("Bill payment from client account", "BILL/{ref}"),
)


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


def _random_due_at() -> datetime | None:
    if random.random() < 0.15:
        return None
    days = random.randint(-14, 45)
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    return base + timedelta(days=days)


def _seed_tasks(
    db,
    *,
    case: Case,
    creator: User,
    users: list[User],
    sub_id: uuid.UUID,
) -> int:
    count = random.randint(10, 20)
    standard = _standard_tasks_for_sub(db, sub_id)
    pool: list[tuple[str, uuid.UUID | None]] = [(st.title, st.id) for st in standard]
    pool.extend((title, None) for title in EXTRA_TASK_TITLES)
    random.shuffle(pool)
    chosen = pool[:count]
    now = datetime.now(timezone.utc)
    for title, std_id in chosen:
        status_roll = random.random()
        if status_roll < 0.55:
            status = CaseTaskStatus.open
        elif status_roll < 0.88:
            status = CaseTaskStatus.done
        else:
            status = CaseTaskStatus.cancelled
        assignee = random.choice(users)
        db.add(
            CaseTask(
                case_id=case.id,
                created_by_user_id=creator.id,
                title=title,
                description=random.choice(
                    (
                        None,
                        None,
                        "Follow up with client if no response within 48 hours.",
                        "Check file and update matter progress note.",
                        "Coordinate with fee earner before chasing third party.",
                    )
                ),
                status=status,
                due_at=_random_due_at(),
                standard_task_id=std_id,
                assigned_to_user_id=assignee.id,
                priority=random.choice(("low", "normal", "normal", "normal", "high")),
                is_private=random.random() < 0.05,
                created_at=now - timedelta(days=random.randint(0, 120)),
                updated_at=now - timedelta(days=random.randint(0, 30)),
            )
        )
    return count


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
    pair_id = post_transaction(
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
    # Backdate posted_at on both legs for a realistic timeline.
    from app.models import LedgerEntry

    legs = db.execute(select(LedgerEntry).where(LedgerEntry.pair_id == pair_id)).scalars().all()
    for leg in legs:
        leg.posted_at = posted_at


def _seed_ledger(
    db,
    *,
    case: Case,
    poster: User,
    client_name: str,
) -> int:
    ref_suffix = case.case_number
    now = datetime.now(timezone.utc)
    client_balance = 0
    count = 0

    receipt_count = random.randint(1, 3)
    for i in range(receipt_count):
        amount = random.choice(
            (50_000, 75_000, 100_000, 125_000, 150_000, 200_000, 250_000, 350_000, 500_000, 750_000, 1_000_000)
        )
        template = random.choice(LEDGER_CLIENT_RECEIPTS)
        posted_at = now - timedelta(days=random.randint(30, 180) - i * 5)
        _post_ledger(
            db,
            case_id=case.id,
            poster=poster,
            amount_pence=amount,
            description=template[0],
            reference=template[1].format(ref=f"{ref_suffix}-{i + 1}"),
            client_direction="credit",
            posted_at=posted_at,
            contact_label=client_name,
        )
        client_balance += amount
        count += 1

    disbursement_count = random.randint(2, 6)
    for i in range(disbursement_count):
        amount = random.choice((2_500, 3_500, 4_500, 6_000, 7_500, 9_500, 12_000, 15_000, 18_000, 25_000))
        template = random.choice(LEDGER_OFFICE_DISBURSEMENTS)
        posted_at = now - timedelta(days=random.randint(10, 120))
        _post_ledger(
            db,
            case_id=case.id,
            poster=poster,
            amount_pence=amount,
            description=template[0],
            reference=template[1].format(ref=f"{ref_suffix}-D{i + 1}"),
            office_direction="debit",
            posted_at=posted_at,
        )
        count += 1

    transfer_count = random.randint(1, 4)
    for i in range(transfer_count):
        max_transfer = max(5_000, int(client_balance * random.uniform(0.05, 0.35)))
        amount = min(max_transfer, random.choice((15_000, 25_000, 40_000, 60_000, 85_000, 120_000)))
        if amount <= 0 or amount > client_balance:
            continue
        template = random.choice(LEDGER_TRANSFERS)
        posted_at = now - timedelta(days=random.randint(5, 90))
        _post_ledger(
            db,
            case_id=case.id,
            poster=poster,
            amount_pence=amount,
            description=template[0],
            reference=template[1].format(ref=f"{ref_suffix}-T{i + 1}"),
            client_direction="debit",
            office_direction="credit",
            posted_at=posted_at,
            contact_label=client_name,
        )
        client_balance -= amount
        count += 1

    if random.random() < 0.25 and client_balance >= 10_000:
        amount = random.choice((5_000, 10_000, 15_000, 20_000))
        if amount <= client_balance:
            template = random.choice(LEDGER_CLIENT_RECEIPTS)
            _post_ledger(
                db,
                case_id=case.id,
                poster=poster,
                amount_pence=amount,
                description=template[0],
                reference=template[1].format(ref=f"{ref_suffix}-TOP"),
                client_direction="credit",
                posted_at=now - timedelta(days=random.randint(1, 14)),
                contact_label=client_name,
            )
            count += 1

    return count


def main() -> None:
    if os.getenv("I_CONFIRM_CANARY_SEED", "").strip().lower() not in ("1", "true", "yes"):
        print("Set I_CONFIRM_CANARY_SEED=yes to run.", file=sys.stderr)
        sys.exit(1)

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

        creator = _pick_poster(users)
        poster = creator
        created_cases: list[Case] = []
        total_tasks = 0
        total_ledger = 0

        for _ in range(SAMPLE_COUNT):
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
                status=random.choice([CaseStatus.open, CaseStatus.open, CaseStatus.open, CaseStatus.quote]),
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
                email=f"{fn.lower()}.{ln.lower()}{random.randint(1, 99)}@example.com",
                phone=f"07{random.randint(100, 999)}{random.randint(100000, 999999)}",
                first_name=fn,
                last_name=ln,
                matter_contact_type=CLIENT_SLUG,
            )
            db.add(cc)
            sync_case_client_name(db, case.id)

            get_finance(case.id, db)
            total_ledger += _seed_ledger(db, case=case, poster=poster, client_name=client_name)
            total_tasks += _seed_tasks(
                db,
                case=case,
                creator=creator,
                users=users,
                sub_id=sub.id,
            )
            created_cases.append(case)

        db.commit()
        print(
            f"Created {len(created_cases)} cases, {total_tasks} tasks, {total_ledger} ledger postings "
            f"(no documents)."
        )
        for c in created_cases[:10]:
            db.refresh(c)
            print(f"  {c.case_number} — {c.client_name or '(no client)'} — {c.title[:60]}…")
        if len(created_cases) > 10:
            print(f"  … and {len(created_cases) - 10} more")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

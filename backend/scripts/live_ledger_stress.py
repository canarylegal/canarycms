#!/usr/bin/env python3
"""Live PostgreSQL concurrency stress for SAR client-account deficit enforcement.

Runs inside the backend container against the real DB:

  python scripts/live_ledger_stress.py

Creates an isolated temporary matter, races concurrent approved debits, and
asserts the client balance never goes negative and exactly one debit of the
full credit succeeds.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db import DATABASE_URL
from app.ledger_service import get_ledger, post_transaction
from app.models import Case, CaseStatus, LedgerAccount, LedgerEntry, User, UserRole
from app.schemas import LedgerPostCreate
from app.timeutil import utcnow


WORKERS = int(os.getenv("LEDGER_STRESS_WORKERS", "24"))
ROUNDS = int(os.getenv("LEDGER_STRESS_ROUNDS", "8"))
CREDIT_PENCE = int(os.getenv("LEDGER_STRESS_CREDIT_PENCE", "10000"))  # £100

# Dedicated engine with enough connections for concurrent workers (app pool is smaller).
_stress_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=max(WORKERS + 4, 16),
    max_overflow=max(WORKERS, 8),
    pool_timeout=60,
)
StressSession = sessionmaker(autocommit=False, autoflush=False, bind=_stress_engine)


def SessionLocal():
    return StressSession()


@dataclass
class Report:
    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")

    @property
    def ok(self) -> bool:
        return all(r[1] for r in self.results)


def _admin(db) -> User:
    user = db.execute(select(User).where(User.role == UserRole.admin, User.is_active.is_(True))).scalars().first()
    if user is None:
        user = db.execute(select(User).where(User.is_active.is_(True))).scalars().first()
    if user is None:
        raise RuntimeError("No active user for ledger stress")
    return user


def _make_case(db, admin: User) -> Case:
    case = Case(
        id=uuid.uuid4(),
        case_number=f"LEDGER-STRESS-{uuid.uuid4().hex[:10]}",
        title="Ledger concurrency stress (auto)",
        fee_earner_user_id=admin.id,
        created_by=admin.id,
        status=CaseStatus.open,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _cleanup_case(case_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        # Child rows first via SQL to avoid ORM identity-map surprises under concurrency.
        db.execute(
            text(
                "DELETE FROM ledger_entry WHERE account_id IN "
                "(SELECT id FROM ledger_account WHERE case_id = CAST(:cid AS uuid))"
            ),
            {"cid": str(case_id)},
        )
        db.execute(text("DELETE FROM ledger_account WHERE case_id = CAST(:cid AS uuid)"), {"cid": str(case_id)})
        db.execute(text('DELETE FROM "case" WHERE id = CAST(:cid AS uuid)'), {"cid": str(case_id)})
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _race_full_debits(case_id: uuid.UUID, user_id: uuid.UUID, amount: int, workers: int) -> tuple[int, int, list[str]]:
    barrier = threading.Barrier(workers, timeout=120)
    ok_count = 0
    fail_count = 0
    lock = threading.Lock()
    errors: list[str] = []

    def worker(idx: int) -> str:
        nonlocal ok_count, fail_count
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            assert user is not None
            barrier.wait()
            try:
                post_transaction(
                    case_id,
                    LedgerPostCreate(
                        description=f"stress debit {idx}",
                        amount_pence=amount,
                        client_direction="debit",
                    ),
                    user,
                    db,
                )
                db.commit()
                with lock:
                    ok_count += 1
                return "ok"
            except HTTPException as exc:
                db.rollback()
                with lock:
                    fail_count += 1
                return f"http-{exc.status_code}"
            except Exception as exc:
                db.rollback()
                with lock:
                    fail_count += 1
                    errors.append(f"w{idx}:{type(exc).__name__}:{exc}")
                return f"err-{type(exc).__name__}"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(worker, i) for i in range(workers)]
        for fut in as_completed(futs):
            fut.result()
    return ok_count, fail_count, errors


def _race_partial_debits(case_id: uuid.UUID, user_id: uuid.UUID, chunk: int, workers: int) -> tuple[int, int]:
    """Each worker tries to debit ``chunk``; total capacity = credit / chunk successes max."""
    barrier = threading.Barrier(workers, timeout=120)
    ok_count = 0
    fail_count = 0
    lock = threading.Lock()

    def worker(idx: int) -> None:
        nonlocal ok_count, fail_count
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            assert user is not None
            barrier.wait()
            try:
                post_transaction(
                    case_id,
                    LedgerPostCreate(
                        description=f"stress partial {idx}",
                        amount_pence=chunk,
                        client_direction="debit",
                    ),
                    user,
                    db,
                )
                db.commit()
                with lock:
                    ok_count += 1
            except HTTPException:
                db.rollback()
                with lock:
                    fail_count += 1
            except Exception:
                db.rollback()
                with lock:
                    fail_count += 1
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(worker, range(workers)))
    return ok_count, fail_count


def main() -> int:
    report = Report()
    print(f"Live ledger stress (workers={WORKERS}, rounds={ROUNDS}, credit={CREDIT_PENCE}p)")
    print()

    db = SessionLocal()
    try:
        # Confirm Postgres locking is available
        dialect = db.bind.dialect.name if db.bind is not None else "?"
        report.add("database is PostgreSQL", dialect == "postgresql", dialect)
        db.execute(text("SELECT 1"))
        admin = _admin(db)
        report.add("resolved staff poster", True, admin.email)
    finally:
        db.close()

    for round_i in range(1, ROUNDS + 1):
        print(f"Round {round_i}/{ROUNDS}")
        db = SessionLocal()
        try:
            admin = _admin(db)
            case = _make_case(db, admin)
            post_transaction(
                case.id,
                LedgerPostCreate(
                    description="stress seed credit",
                    amount_pence=CREDIT_PENCE,
                    client_direction="credit",
                ),
                admin,
                db,
            )
            db.commit()
            case_id = case.id
            user_id = admin.id
        finally:
            db.close()

        try:
            ok_n, fail_n, errors = _race_full_debits(case_id, user_id, CREDIT_PENCE, WORKERS)
            db = SessionLocal()
            try:
                bal = get_ledger(case_id, db).client.balance_pence
            finally:
                db.close()

            report.add(
                f"r{round_i} exactly one full debit succeeds",
                ok_n == 1 and fail_n == WORKERS - 1,
                f"ok={ok_n} fail={fail_n} bal={bal}",
            )
            report.add(
                f"r{round_i} client balance never negative",
                bal >= 0,
                f"bal={bal}",
            )
            report.add(
                f"r{round_i} balance is zero after single full spend",
                bal == 0,
                f"bal={bal}",
            )
            if errors:
                report.add(f"r{round_i} no unexpected errors", False, "; ".join(errors[:3]))
            else:
                report.add(f"r{round_i} no unexpected errors", True)
        finally:
            _cleanup_case(case_id)

    # Partial debit race: £100 credit, 20 workers each debit £10 → exactly 10 succeed
    print()
    print("Partial debit contention")
    db = SessionLocal()
    try:
        admin = _admin(db)
        case = _make_case(db, admin)
        post_transaction(
            case.id,
            LedgerPostCreate(
                description="partial seed",
                amount_pence=CREDIT_PENCE,
                client_direction="credit",
            ),
            admin,
            db,
        )
        db.commit()
        case_id = case.id
        user_id = admin.id
    finally:
        db.close()

    try:
        chunk = CREDIT_PENCE // 10
        workers = 20
        ok_n, fail_n = _race_partial_debits(case_id, user_id, chunk, workers)
        db = SessionLocal()
        try:
            bal = get_ledger(case_id, db).client.balance_pence
        finally:
            db.close()
        expected_ok = CREDIT_PENCE // chunk
        report.add(
            "partial race: exact capacity successes",
            ok_n == expected_ok and bal == 0,
            f"ok={ok_n} expected={expected_ok} fail={fail_n} bal={bal}",
        )
        report.add("partial race: never negative", bal >= 0, f"bal={bal}")
    finally:
        _cleanup_case(case_id)

    # Account creation race: many threads first-touch accounts for a new case
    print()
    print("Account create race")
    db = SessionLocal()
    try:
        admin = _admin(db)
        case = _make_case(db, admin)
        case_id = case.id
        user_id = admin.id
    finally:
        db.close()

    try:
        barrier = threading.Barrier(16, timeout=120)
        errs: list[str] = []

        def create_worker(i: int) -> None:
            s = SessionLocal()
            try:
                user = s.get(User, user_id)
                barrier.wait()
                post_transaction(
                    case_id,
                    LedgerPostCreate(
                        description=f"create-race {i}",
                        amount_pence=1,
                        client_direction="credit",
                    ),
                    user,
                    s,
                )
                s.commit()
            except Exception as exc:
                s.rollback()
                errs.append(f"{type(exc).__name__}:{exc}")
            finally:
                s.close()

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(create_worker, range(16)))

        db = SessionLocal()
        try:
            accounts = db.execute(select(LedgerAccount).where(LedgerAccount.case_id == case_id)).scalars().all()
            bal = get_ledger(case_id, db).client.balance_pence
        finally:
            db.close()
        report.add("create race: exactly two accounts", len(accounts) == 2, f"n={len(accounts)}")
        report.add("create race: all credits applied", bal == 16 and not errs, f"bal={bal} errs={errs[:2]}")
    finally:
        _cleanup_case(case_id)

    # Concurrent approve race: two pending debits that cannot both fit
    print()
    print("Concurrent approve race")
    db = SessionLocal()
    try:
        admin = _admin(db)
        case = _make_case(db, admin)
        post_transaction(
            case.id,
            LedgerPostCreate(description="approve-race credit", amount_pence=CREDIT_PENCE, client_direction="credit"),
            admin,
            db,
        )
        from app.ledger_service import approve_ledger_pair

        p1 = post_transaction(
            case.id,
            LedgerPostCreate(description="pending A", amount_pence=CREDIT_PENCE, client_direction="debit"),
            admin,
            db,
            force_unapproved=True,
        ).pair_id
        p2 = post_transaction(
            case.id,
            LedgerPostCreate(description="pending B", amount_pence=CREDIT_PENCE, client_direction="debit"),
            admin,
            db,
            force_unapproved=True,
        ).pair_id
        db.commit()
        case_id = case.id
        user_id = admin.id
        pair_ids = (p1, p2)
    finally:
        db.close()

    try:
        barrier = threading.Barrier(2, timeout=120)
        outcomes: list[str] = []
        lock = threading.Lock()

        def approve_worker(pair_id: uuid.UUID) -> None:
            s = SessionLocal()
            try:
                user = s.get(User, user_id)
                barrier.wait()
                try:
                    approve_ledger_pair(case_id, pair_id, user, s)
                    s.commit()
                    with lock:
                        outcomes.append("ok")
                except HTTPException as exc:
                    s.rollback()
                    with lock:
                        outcomes.append(f"http-{exc.status_code}")
                except Exception as exc:
                    s.rollback()
                    with lock:
                        outcomes.append(f"err-{type(exc).__name__}")
            finally:
                s.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(approve_worker, pid) for pid in pair_ids]
            for fut in as_completed(futs):
                fut.result()

        db = SessionLocal()
        try:
            bal = get_ledger(case_id, db).client.balance_pence
        finally:
            db.close()
        ok_n = sum(1 for o in outcomes if o == "ok")
        report.add(
            "approve race: exactly one approval succeeds",
            ok_n == 1 and bal == 0,
            f"outcomes={outcomes} bal={bal}",
        )
        report.add("approve race: never negative", bal >= 0, f"bal={bal}")
    finally:
        _cleanup_case(case_id)

    print()
    passed = sum(1 for _, ok, _ in report.results if ok)
    total = len(report.results)
    print(f"Result: {passed}/{total} passed")
    return 0 if report.ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)

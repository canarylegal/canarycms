"""Client account end-of-month pack (ZIP of CSV reports + optional recon)."""
from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bank_accounts_service import get_bank_account
from app.bank_recon_service import list_bank_reconciliations, unpresented_client_legs
from app.models import (
    BankStatementLine,
    Case,
    ClientAccountEom,
    InterMatterJournal,
    LedgerAccount,
    LedgerAccountType,
    LedgerEntry,
    User,
)


def _csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def _trial_balance_rows(db: Session, firm_bank_account_id: uuid.UUID, as_of: date) -> list[list]:
    q = (
        select(Case.case_number, Case.id, LedgerEntry.direction, LedgerEntry.amount_pence)
        .join(LedgerAccount, LedgerAccount.case_id == Case.id)
        .join(LedgerEntry, LedgerEntry.account_id == LedgerAccount.id)
        .where(
            LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True),
            LedgerEntry.firm_bank_account_id == firm_bank_account_id,
            LedgerEntry.posted_at < datetime.combine(as_of, datetime.max.time()).replace(tzinfo=timezone.utc),
        )
    )
    # Fallback: also include legs with null bank (legacy) when this is the default bank
    balances: dict[str, int] = {}
    for case_number, _cid, direction, amount in db.execute(q).all():
        key = case_number or str(_cid)
        delta = int(amount) if direction.value == "credit" else -int(amount)
        balances[key] = balances.get(key, 0) + delta
    rows = [[k, f"{v / 100:.2f}"] for k, v in sorted(balances.items()) if v != 0]
    rows.append(["TOTAL", f"{sum(balances.values()) / 100:.2f}"])
    return rows


def _cashbook_rows(
    db: Session,
    firm_bank_account_id: uuid.UUID,
    period_end: date,
    *,
    receipts: bool,
) -> list[list]:
    q = (
        select(LedgerEntry, Case)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .join(Case, Case.id == LedgerAccount.case_id)
        .where(
            LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True),
            LedgerEntry.firm_bank_account_id == firm_bank_account_id,
            LedgerEntry.posted_at
            >= datetime(period_end.year, period_end.month, 1, tzinfo=timezone.utc),
            LedgerEntry.posted_at
            < datetime.combine(period_end, datetime.max.time()).replace(tzinfo=timezone.utc),
        )
        .order_by(LedgerEntry.posted_at)
    )
    want = "credit" if receipts else "debit"
    out: list[list] = []
    for e, case in db.execute(q).all():
        if e.direction.value != want:
            continue
        out.append(
            [
                e.posted_at.date().isoformat(),
                case.case_number or "",
                e.description,
                e.reference or "",
                e.payment_method or "",
                f"{e.amount_pence / 100:.2f}",
            ]
        )
    return out


def _overdrawn_rows(db: Session, firm_bank_account_id: uuid.UUID) -> list[list]:
    tb = _trial_balance_rows(db, firm_bank_account_id, date.today())
    return [r for r in tb if r[0] != "TOTAL" and float(r[1]) < 0]


def _journals_rows(db: Session, period_end: date) -> list[list]:
    start = datetime(period_end.year, period_end.month, 1, tzinfo=timezone.utc)
    end = datetime.combine(period_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    q = (
        select(InterMatterJournal)
        .where(InterMatterJournal.created_at >= start, InterMatterJournal.created_at <= end)
        .order_by(InterMatterJournal.created_at)
    )
    rows: list[list] = []
    for j in db.execute(q).scalars().all():
        rows.append(
            [
                j.created_at.date().isoformat(),
                str(j.from_case_id),
                str(j.to_case_id),
                j.description,
                f"{j.amount_pence / 100:.2f}",
            ]
        )
    return rows


def build_eom_zip(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID,
    period_end_date: date,
) -> tuple[bytes, str]:
    bank = get_bank_account(db, firm_bank_account_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "01_trial_balance.csv",
            _csv_bytes(["Matter", "Balance_GBP"], _trial_balance_rows(db, firm_bank_account_id, period_end_date)),
        )
        zf.writestr(
            "02_receipts_cashbook.csv",
            _csv_bytes(
                ["Date", "Matter", "Description", "Reference", "Method", "Amount_GBP"],
                _cashbook_rows(db, firm_bank_account_id, period_end_date, receipts=True),
            ),
        )
        zf.writestr(
            "03_payments_cashbook.csv",
            _csv_bytes(
                ["Date", "Matter", "Description", "Reference", "Method", "Amount_GBP"],
                _cashbook_rows(db, firm_bank_account_id, period_end_date, receipts=False),
            ),
        )
        zf.writestr(
            "04_overdrawn_clients.csv",
            _csv_bytes(["Matter", "Balance_GBP"], _overdrawn_rows(db, firm_bank_account_id)),
        )
        zf.writestr(
            "05_inter_matter_journals.csv",
            _csv_bytes(
                ["Date", "FromCaseId", "ToCaseId", "Description", "Amount_GBP"],
                _journals_rows(db, period_end_date),
            ),
        )
        unp = unpresented_client_legs(db, firm_bank_account_id=firm_bank_account_id, as_of=period_end_date)
        zf.writestr(
            "06_unpresented.csv",
            _csv_bytes(
                ["Date", "Matter", "Description", "Direction", "Amount_GBP", "Reference"],
                [
                    [
                        u["posted_at"].date().isoformat(),
                        u.get("case_number") or "",
                        u["description"],
                        u["direction"],
                        f"{u['amount_pence'] / 100:.2f}",
                        u.get("reference") or "",
                    ]
                    for u in unp
                ],
            ),
        )
        unmatched = db.execute(
            select(BankStatementLine).where(
                BankStatementLine.firm_bank_account_id == firm_bank_account_id,
                BankStatementLine.matched_pair_id.is_(None),
                BankStatementLine.ignored.is_(False),
                BankStatementLine.statement_date <= period_end_date,
            )
        ).scalars().all()
        zf.writestr(
            "07_unmatched_statement.csv",
            _csv_bytes(
                ["Date", "Description", "Reference", "Amount_GBP"],
                [
                    [
                        l.statement_date.isoformat(),
                        l.description,
                        l.reference or "",
                        f"{l.amount_pence / 100:.2f}",
                    ]
                    for l in unmatched
                ],
            ),
        )
        recs = [
            r
            for r in list_bank_reconciliations(db, firm_bank_account_id=firm_bank_account_id)
            if r.period_end_date == period_end_date
        ]
        zf.writestr(
            "08_reconciliation_summary.csv",
            _csv_bytes(
                [
                    "PeriodEnd",
                    "Status",
                    "StatementBalance",
                    "LedgerTotal",
                    "Unpresented",
                    "UnmatchedStatement",
                    "Difference",
                    "Notes",
                ],
                [
                    [
                        r.period_end_date.isoformat(),
                        r.status,
                        f"{r.statement_balance_pence / 100:.2f}",
                        f"{r.ledger_total_pence / 100:.2f}",
                        f"{r.unpresented_total_pence / 100:.2f}",
                        f"{r.unmatched_statement_total_pence / 100:.2f}",
                        f"{r.difference_pence / 100:.2f}",
                        r.notes or "",
                    ]
                    for r in recs
                ]
                or [[period_end_date.isoformat(), "none", "", "", "", "", "", "No reconciliation saved"]],
            ),
        )
        zf.writestr(
            "README.txt",
            (
                f"Client account EOM pack\n"
                f"Bank: {bank.name}\n"
                f"Period end: {period_end_date.isoformat()}\n"
                f"Generated: {datetime.now(timezone.utc).isoformat()}\n"
            ).encode("utf-8"),
        )
    safe = re_sub_safe(bank.name)
    filename = f"client-account-eom-{safe}-{period_end_date.isoformat()}.zip"
    return buf.getvalue(), filename


def re_sub_safe(name: str) -> str:
    return re.sub(r"[^\w\-]+", "-", (name or "bank").strip())[:40].strip("-") or "bank"


def create_or_replace_eom(
    db: Session,
    *,
    actor: User,
    firm_bank_account_id: uuid.UUID,
    period_end_date: date,
    notes: str | None,
) -> ClientAccountEom:
    content, filename = build_eom_zip(
        db, firm_bank_account_id=firm_bank_account_id, period_end_date=period_end_date
    )
    existing = db.execute(
        select(ClientAccountEom).where(
            ClientAccountEom.firm_bank_account_id == firm_bank_account_id,
            ClientAccountEom.period_end_date == period_end_date,
        )
    ).scalar_one_or_none()
    if existing:
        existing.content = content
        existing.filename = filename
        existing.generated_by_user_id = actor.id
        existing.generated_at = datetime.now(timezone.utc)
        existing.notes = notes
        db.add(existing)
        db.flush()
        return existing
    row = ClientAccountEom(
        id=uuid.uuid4(),
        firm_bank_account_id=firm_bank_account_id,
        period_end_date=period_end_date,
        generated_by_user_id=actor.id,
        generated_at=datetime.now(timezone.utc),
        filename=filename,
        content=content,
        content_type="application/zip",
        notes=notes,
    )
    db.add(row)
    db.flush()
    return row


def list_eoms(db: Session, *, firm_bank_account_id: uuid.UUID | None = None) -> list[ClientAccountEom]:
    q = select(ClientAccountEom).order_by(ClientAccountEom.period_end_date.desc()).limit(48)
    if firm_bank_account_id:
        q = q.where(ClientAccountEom.firm_bank_account_id == firm_bank_account_id)
    return list(db.execute(q).scalars().all())


def get_eom(db: Session, eom_id: uuid.UUID) -> ClientAccountEom:
    row = db.get(ClientAccountEom, eom_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EOM pack not found")
    return row

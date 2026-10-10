"""CSV/OFX bank statement import and line-level matching."""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timezone
from xml.etree import ElementTree as ET

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BankReconciliation,
    BankStatementImport,
    BankStatementLine,
    Case,
    LedgerAccount,
    LedgerAccountType,
    LedgerEntry,
    User,
)
from app.permission_checks import user_may_approve_ledger
from app.bank_accounts_service import get_bank_account


def _parse_uk_date(raw: str) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount_to_pence(raw: str) -> int | None:
    s = (raw or "").strip().replace("£", "").replace(",", "")
    if not s:
        return None
    # parentheses = negative
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    try:
        pounds = float(s)
    except ValueError:
        return None
    pence = int(round(pounds * 100))
    return -pence if neg else pence


def parse_statement_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")
    fields = {((f or "").strip().lower()): (f or "") for f in reader.fieldnames}

    def col(*names: str) -> str | None:
        for n in names:
            if n in fields:
                return fields[n]
        return None

    date_col = col("date", "transaction date", "value date", "posted")
    desc_col = col("description", "narrative", "details", "memo")
    ref_col = col("reference", "ref", "cheque", "cheque number")
    amount_col = col("amount", "value", "transaction amount")
    credit_col = col("credit", "money in", "paid in", "deposit")
    debit_col = col("debit", "money out", "paid out", "withdrawal", "payment")
    bal_col = col("balance", "running balance")

    if not date_col or (not amount_col and not credit_col and not debit_col):
        raise HTTPException(
            status_code=400,
            detail="CSV must include Date and Amount (or Credit/Debit) columns",
        )

    rows: list[dict] = []
    for r in reader:
        d = _parse_uk_date(r.get(date_col, ""))
        if d is None:
            continue
        if amount_col:
            amt = _parse_amount_to_pence(r.get(amount_col, ""))
        else:
            credit = _parse_amount_to_pence(r.get(credit_col, "")) if credit_col else None
            debit = _parse_amount_to_pence(r.get(debit_col, "")) if debit_col else None
            if credit and credit != 0:
                amt = abs(credit)
            elif debit and debit != 0:
                amt = -abs(debit)
            else:
                continue
        if amt is None or amt == 0:
            continue
        bal = _parse_amount_to_pence(r.get(bal_col, "")) if bal_col else None
        rows.append(
            {
                "statement_date": d,
                "amount_pence": amt,
                "description": (r.get(desc_col, "") if desc_col else "").strip() or "Bank transaction",
                "reference": ((r.get(ref_col, "") if ref_col else "").strip() or None),
                "balance_pence": bal,
            }
        )
    if not rows:
        raise HTTPException(status_code=400, detail="No usable statement lines found in CSV")
    return rows


def parse_statement_ofx(content: bytes) -> list[dict]:
    text = content.decode("utf-8", errors="replace")
    idx = text.upper().find("<OFX")
    if idx < 0:
        raise HTTPException(status_code=400, detail="Not a recognised OFX file")
    body = text[idx:]
    rows: list[dict] = []

    def _field(block: str, name: str) -> str:
        m = re.search(rf"<{name}>([^<\r\n]+)", block, flags=re.I)
        return (m.group(1).strip() if m else "")

    for m in re.finditer(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", body, flags=re.I | re.S):
        block = m.group(1)
        dt_raw = _field(block, "DTPOSTED") or _field(block, "DTUSER")
        if len(dt_raw) < 8:
            continue
        try:
            d = date(int(dt_raw[0:4]), int(dt_raw[4:6]), int(dt_raw[6:8]))
        except ValueError:
            continue
        amt = _parse_amount_to_pence(_field(block, "TRNAMT"))
        if amt is None or amt == 0:
            continue
        rows.append(
            {
                "statement_date": d,
                "amount_pence": amt,
                "description": _field(block, "NAME") or _field(block, "MEMO") or "Bank transaction",
                "reference": _field(block, "CHECKNUM") or _field(block, "FITID") or None,
                "balance_pence": None,
            }
        )
    if rows:
        return rows

    # Fallback: try XML parse for well-formed OFX
    xml = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", body)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse OFX: {exc}") from exc
    for txn in root.iter():
        tag = (txn.tag or "").split("}")[-1].upper()
        if tag != "STMTTRN":
            continue
        children = {(c.tag or "").split("}")[-1].upper(): (c.text or "").strip() for c in list(txn)}
        dt_raw = children.get("DTPOSTED") or children.get("DTUSER") or ""
        if len(dt_raw) < 8:
            continue
        try:
            d = date(int(dt_raw[0:4]), int(dt_raw[4:6]), int(dt_raw[6:8]))
        except ValueError:
            continue
        amt = _parse_amount_to_pence(children.get("TRNAMT", ""))
        if amt is None or amt == 0:
            continue
        rows.append(
            {
                "statement_date": d,
                "amount_pence": amt,
                "description": children.get("NAME") or children.get("MEMO") or "Bank transaction",
                "reference": children.get("CHECKNUM") or children.get("FITID") or None,
                "balance_pence": None,
            }
        )
    if not rows:
        raise HTTPException(status_code=400, detail="No transactions found in OFX")
    return rows


def import_statement(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID,
    filename: str | None,
    content: bytes,
    actor: User,
) -> BankStatementImport:
    get_bank_account(db, firm_bank_account_id)
    name = (filename or "").lower()
    if name.endswith(".ofx") or name.endswith(".qfx") or content.lstrip()[:1] in (b"<", b"O"):
        try:
            parsed = parse_statement_ofx(content)
        except HTTPException:
            if name.endswith(".csv") or b"," in content[:200]:
                parsed = parse_statement_csv(content)
            else:
                raise
    else:
        parsed = parse_statement_csv(content)

    imp = BankStatementImport(
        id=uuid.uuid4(),
        firm_bank_account_id=firm_bank_account_id,
        filename=filename,
        imported_by_user_id=actor.id,
        imported_at=datetime.now(timezone.utc),
        line_count=len(parsed),
    )
    db.add(imp)
    db.flush()
    for p in parsed:
        db.add(
            BankStatementLine(
                id=uuid.uuid4(),
                import_id=imp.id,
                firm_bank_account_id=firm_bank_account_id,
                statement_date=p["statement_date"],
                amount_pence=p["amount_pence"],
                description=p["description"],
                reference=p.get("reference"),
                balance_pence=p.get("balance_pence"),
            )
        )
    db.flush()
    return imp


def list_statement_lines(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID,
    unmatched_only: bool = False,
    limit: int = 500,
) -> list[BankStatementLine]:
    q = (
        select(BankStatementLine)
        .where(BankStatementLine.firm_bank_account_id == firm_bank_account_id)
        .order_by(BankStatementLine.statement_date.desc(), BankStatementLine.created_at.desc())
        .limit(limit)
    )
    if unmatched_only:
        q = q.where(BankStatementLine.matched_pair_id.is_(None), BankStatementLine.ignored.is_(False))
    return list(db.execute(q).scalars().all())


def match_line(
    db: Session,
    *,
    line_id: uuid.UUID,
    ledger_pair_id: uuid.UUID,
    actor: User,
) -> BankStatementLine:
    line = db.get(BankStatementLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Statement line not found")
    # Ensure pair exists on a client ledger leg for this bank (or any client leg).
    leg = db.execute(
        select(LedgerEntry)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .where(
            LedgerEntry.pair_id == ledger_pair_id,
            LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if leg is None:
        raise HTTPException(status_code=400, detail="Ledger pair not found on an approved client posting")
    line.matched_pair_id = ledger_pair_id
    line.matched_at = datetime.now(timezone.utc)
    line.matched_by_user_id = actor.id
    line.ignored = False
    db.add(line)
    db.flush()
    return line


def unmatch_line(db: Session, *, line_id: uuid.UUID) -> BankStatementLine:
    line = db.get(BankStatementLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Statement line not found")
    line.matched_pair_id = None
    line.matched_at = None
    line.matched_by_user_id = None
    db.add(line)
    db.flush()
    return line


def ignore_line(db: Session, *, line_id: uuid.UUID, ignored: bool = True) -> BankStatementLine:
    line = db.get(BankStatementLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Statement line not found")
    line.ignored = bool(ignored)
    if ignored:
        line.matched_pair_id = None
        line.matched_at = None
        line.matched_by_user_id = None
    db.add(line)
    db.flush()
    return line


def unpresented_client_legs(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID,
    as_of: date | None = None,
) -> list[dict]:
    """Approved client legs on this bank that are not matched to a statement line."""
    matched_pairs = select(BankStatementLine.matched_pair_id).where(
        BankStatementLine.firm_bank_account_id == firm_bank_account_id,
        BankStatementLine.matched_pair_id.is_not(None),
    )
    q = (
        select(LedgerEntry, LedgerAccount, Case)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .join(Case, Case.id == LedgerAccount.case_id)
        .where(
            LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True),
            LedgerEntry.is_anticipated.is_(False),
            LedgerEntry.firm_bank_account_id == firm_bank_account_id,
            LedgerEntry.pair_id.not_in(matched_pairs),
        )
        .order_by(LedgerEntry.posted_at.desc())
        .limit(500)
    )
    out: list[dict] = []
    for e, _acc, case in db.execute(q).all():
        if as_of and e.posted_at.date() > as_of:
            continue
        out.append(
            {
                "pair_id": e.pair_id,
                "case_id": case.id,
                "case_number": case.case_number,
                "posted_at": e.posted_at,
                "amount_pence": e.amount_pence,
                "direction": e.direction.value,
                "description": e.description,
                "reference": e.reference,
                "payment_method": e.payment_method,
            }
        )
    return out


def _bank_ledger_total_pence(db: Session, firm_bank_account_id: uuid.UUID) -> int:
    """Sum of approved client legs tagged to this bank (credit − debit)."""
    rows = db.execute(
        select(LedgerEntry.direction, LedgerEntry.amount_pence)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .where(
            LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True),
            LedgerEntry.firm_bank_account_id == firm_bank_account_id,
        )
    ).all()
    total = 0
    for direction, amount in rows:
        if direction.value == "credit":
            total += int(amount)
        else:
            total -= int(amount)
    return total


def compute_recon_totals(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID,
    statement_balance_pence: int,
    period_end_date: date,
) -> dict[str, int]:
    ledger_total = _bank_ledger_total_pence(db, firm_bank_account_id)
    unmatched_lines = list_statement_lines(db, firm_bank_account_id=firm_bank_account_id, unmatched_only=True)
    unmatched_statement = sum(int(l.amount_pence) for l in unmatched_lines if l.statement_date <= period_end_date)
    unpresented = 0
    for leg in unpresented_client_legs(db, firm_bank_account_id=firm_bank_account_id, as_of=period_end_date):
        # Client credit = money held; debit = money out. Unpresented adjusts toward bank.
        if leg["direction"] == "credit":
            unpresented += int(leg["amount_pence"])
        else:
            unpresented -= int(leg["amount_pence"])
    # Bank = ledger − unpresented + unmatched statement (simplified three-way)
    difference = int(statement_balance_pence) - ledger_total + unpresented - unmatched_statement
    return {
        "ledger_total_pence": ledger_total,
        "unpresented_total_pence": unpresented,
        "unmatched_statement_total_pence": unmatched_statement,
        "difference_pence": difference,
    }


def create_bank_reconciliation(
    db: Session,
    *,
    actor: User,
    firm_bank_account_id: uuid.UUID,
    period_end_date: date,
    statement_balance_pence: int,
    notes: str | None,
) -> BankReconciliation:
    get_bank_account(db, firm_bank_account_id)
    existing = db.execute(
        select(BankReconciliation).where(
            BankReconciliation.firm_bank_account_id == firm_bank_account_id,
            BankReconciliation.period_end_date == period_end_date,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Reconciliation already exists for this period")
    totals = compute_recon_totals(
        db,
        firm_bank_account_id=firm_bank_account_id,
        statement_balance_pence=statement_balance_pence,
        period_end_date=period_end_date,
    )
    row = BankReconciliation(
        id=uuid.uuid4(),
        firm_bank_account_id=firm_bank_account_id,
        period_end_date=period_end_date,
        statement_balance_pence=statement_balance_pence,
        ledger_total_pence=totals["ledger_total_pence"],
        unpresented_total_pence=totals["unpresented_total_pence"],
        unmatched_statement_total_pence=totals["unmatched_statement_total_pence"],
        difference_pence=totals["difference_pence"],
        status="draft",
        notes=notes,
        prepared_by_user_id=actor.id,
        prepared_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def refresh_bank_reconciliation(db: Session, row: BankReconciliation) -> BankReconciliation:
    if row.status == "approved":
        raise HTTPException(status_code=400, detail="Approved reconciliations cannot be refreshed")
    totals = compute_recon_totals(
        db,
        firm_bank_account_id=row.firm_bank_account_id,
        statement_balance_pence=row.statement_balance_pence,
        period_end_date=row.period_end_date,
    )
    row.ledger_total_pence = totals["ledger_total_pence"]
    row.unpresented_total_pence = totals["unpresented_total_pence"]
    row.unmatched_statement_total_pence = totals["unmatched_statement_total_pence"]
    row.difference_pence = totals["difference_pence"]
    db.add(row)
    db.flush()
    return row


def approve_bank_reconciliation(db: Session, *, actor: User, row: BankReconciliation) -> BankReconciliation:
    if not user_may_approve_ledger(actor, db):
        raise HTTPException(status_code=403, detail="Not permitted to approve reconciliations")
    if row.status == "approved":
        return row
    if row.difference_pence != 0 and not (row.notes or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Notes are required when the reconciliation difference is not zero",
        )
    refresh_bank_reconciliation(db, row)
    row.status = "approved"
    row.approved_by_user_id = actor.id
    row.approved_at = datetime.now(timezone.utc)
    db.add(row)
    db.flush()
    return row


def list_bank_reconciliations(db: Session, *, firm_bank_account_id: uuid.UUID | None = None) -> list[BankReconciliation]:
    q = select(BankReconciliation).order_by(BankReconciliation.period_end_date.desc()).limit(48)
    if firm_bank_account_id:
        q = q.where(BankReconciliation.firm_bank_account_id == firm_bank_account_id)
    return list(db.execute(q).scalars().all())

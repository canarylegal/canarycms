"""CSV/OFX bank statement import and line-level matching."""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timezone, timedelta, time
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

from fastapi import HTTPException, status
from sqlalchemy import select, func, case as sql_case
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
from app.audit import log_event
from app.bank_integrity import lock_bank, require_banking, require_open_period
from app.bank_matching_service import match_line, unmatch_line, ignore_line, line_history, restore_line
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
        pounds = Decimal(s)
        scaled = pounds * 100
        if not scaled.is_finite() or scaled != scaled.to_integral_value() or abs(scaled) > 2147483647:
            raise HTTPException(400, "Amounts must be finite whole pence within the supported range")
        pence = int(scaled)
    except InvalidOperation:
        return None
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
    for row_number, r in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in r.values()):
            continue
        d = _parse_uk_date(r.get(date_col, ""))
        if d is None:
            raise HTTPException(400, f"Invalid statement date on CSV row {row_number}")
        if amount_col:
            amt = _parse_amount_to_pence(r.get(amount_col, ""))
        else:
            credit = _parse_amount_to_pence(r.get(credit_col, "")) if credit_col else None
            debit = _parse_amount_to_pence(r.get(debit_col, "")) if debit_col else None
            if credit and debit:
                raise HTTPException(400, f"Both credit and debit are set on CSV row {row_number}")
            if credit and credit != 0:
                amt = abs(credit)
            elif debit and debit != 0:
                amt = -abs(debit)
            else:
                amt = 0 if credit == 0 or debit == 0 else None
        if amt is None:
            raise HTTPException(400, f"Invalid statement amount on CSV row {row_number}")
        if amt == 0:
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
    require_banking(actor, db)
    lock_bank(db, firm_bank_account_id)
    bank = get_bank_account(db, firm_bank_account_id)
    if bank.account_kind != 'client':
        raise HTTPException(400, 'Client bank account required')
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

    require_open_period(db, firm_bank_account_id, min(row['statement_date'] for row in parsed))
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
    log_event(db, actor_user_id=actor.id, action='bank.statement.import', entity_type='bank_statement_import',
              entity_id=str(imp.id), meta={'bank_id': str(firm_bank_account_id), 'line_count': len(parsed)})
    return imp


def list_statement_lines(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID,
    unmatched_only: bool = False,
    limit: int | None = 500,
    import_id: uuid.UUID | None = None,
) -> list[BankStatementLine]:
    q = (
        select(BankStatementLine)
        .where(BankStatementLine.firm_bank_account_id == firm_bank_account_id)
        .order_by(BankStatementLine.statement_date.desc(), BankStatementLine.created_at.desc())
        .limit(limit)
    )
    if import_id is not None:
        q = q.where(BankStatementLine.import_id == import_id)
    if unmatched_only:
        q = q.where(BankStatementLine.matched_pair_id.is_(None), BankStatementLine.ignored.is_(False))
    return list(db.execute(q).scalars().all())


def unpresented_client_legs(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID,
    as_of: date | None = None,
) -> list[dict]:
    """Approved client legs on this bank that are not matched to a statement line."""
    matched_pairs = select(BankStatementLine.matched_pair_id).where(
        BankStatementLine.firm_bank_account_id == firm_bank_account_id,
        BankStatementLine.ignored.is_(False),
        BankStatementLine.matched_pair_id.is_not(None))
    if as_of:
        matched_pairs = matched_pairs.where(BankStatementLine.statement_date <= as_of)
    q = (select(LedgerEntry, LedgerAccount, Case)
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .join(Case, Case.id == LedgerAccount.case_id)
        .where(LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True), LedgerEntry.is_anticipated.is_(False),
            LedgerEntry.firm_bank_account_id == firm_bank_account_id,
            LedgerEntry.pair_id.not_in(matched_pairs))
        .order_by(LedgerEntry.posted_at.desc(), LedgerEntry.id))
    if as_of:
        q = q.where(LedgerEntry.posted_at < _cutoff(as_of))
    out: list[dict] = []
    for e, _acc, case in db.execute(q).all():
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


def _cutoff(period_end_date: date) -> datetime:
    return datetime.combine(period_end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)


def compute_recon_totals(db: Session, *, firm_bank_account_id: uuid.UUID,
                         statement_balance_pence: int, period_end_date: date) -> dict[str, int]:
    """All sums share one SQL snapshot, with UTC period boundaries and no display limits."""
    lock_bank(db, firm_bank_account_id)
    bank = get_bank_account(db, firm_bank_account_id)
    if bank.account_kind != 'client':
        raise HTTPException(400, 'Client bank account required')
    signed = sql_case((LedgerEntry.direction == 'credit', LedgerEntry.amount_pence), else_=-LedgerEntry.amount_pence)
    valid_leg_count = (select(func.count()).select_from(LedgerEntry).join(LedgerAccount)
        .where(LedgerEntry.pair_id == BankStatementLine.matched_pair_id,
            LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True), LedgerEntry.is_anticipated.is_(False),
            LedgerEntry.amount_pence > 0, LedgerEntry.firm_bank_account_id == firm_bank_account_id,
            signed == BankStatementLine.amount_pence).correlate(BankStatementLine).scalar_subquery())
    client_leg_count = (select(func.count()).select_from(LedgerEntry).join(LedgerAccount)
        .where(LedgerEntry.pair_id == BankStatementLine.matched_pair_id,
            LedgerAccount.account_type == LedgerAccountType.client)
        .correlate(BankStatementLine).scalar_subquery())
    invalid_match = db.scalar(select(BankStatementLine.id).where(
        BankStatementLine.firm_bank_account_id == firm_bank_account_id,
        BankStatementLine.statement_date <= period_end_date,
        BankStatementLine.matched_pair_id.is_not(None),
        (valid_leg_count != 1) | (client_leg_count != 1) | BankStatementLine.ignored.is_(True)).limit(1))
    if invalid_match:
        raise HTTPException(409, 'Existing bank matches need review before reconciliation')
    eligible = (select(LedgerEntry.pair_id.label('pair_id'), signed.label('amount'))
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .where(LedgerAccount.account_type == LedgerAccountType.client,
            LedgerEntry.is_approved.is_(True), LedgerEntry.is_anticipated.is_(False),
            LedgerEntry.firm_bank_account_id == firm_bank_account_id,
            LedgerEntry.posted_at < _cutoff(period_end_date)).cte('eligible_ledger'))
    statement = (select(BankStatementLine.matched_pair_id.label('pair_id'), BankStatementLine.amount_pence.label('amount'))
        .where(BankStatementLine.firm_bank_account_id == firm_bank_account_id,
            BankStatementLine.statement_date <= period_end_date, BankStatementLine.ignored.is_(False)).cte('statement'))
    matched_statement = select(statement.c.pair_id).where(statement.c.pair_id == eligible.c.pair_id,
        statement.c.amount == eligible.c.amount).exists()
    matched_ledger = select(eligible.c.pair_id).where(eligible.c.pair_id == statement.c.pair_id,
        eligible.c.amount == statement.c.amount).exists()
    ledger_sum = select(func.coalesce(func.sum(eligible.c.amount), 0)).scalar_subquery()
    unpresented_sum = select(func.coalesce(func.sum(eligible.c.amount), 0)).where(~matched_statement).scalar_subquery()
    unmatched_sum = select(func.coalesce(func.sum(statement.c.amount), 0)).where(~matched_ledger).scalar_subquery()
    ledger_total, unpresented, unmatched = db.execute(select(ledger_sum, unpresented_sum, unmatched_sum)).one()
    return {'ledger_total_pence': int(ledger_total), 'unpresented_total_pence': int(unpresented),
            'unmatched_statement_total_pence': int(unmatched),
            'difference_pence': int(statement_balance_pence) - int(ledger_total) + int(unpresented) - int(unmatched)}


def create_bank_reconciliation(
    db: Session,
    *,
    actor: User,
    firm_bank_account_id: uuid.UUID,
    period_end_date: date,
    statement_balance_pence: int,
    notes: str | None,
) -> BankReconciliation:
    require_banking(actor, db)
    lock_bank(db, firm_bank_account_id)
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
    _audit_recon(db, row, actor, 'create')
    return row


def _recon_snapshot(row: BankReconciliation) -> dict:
    return {key: str(getattr(row, key)) if key.endswith('_at') and getattr(row, key) else getattr(row, key)
            for key in ('status', 'version', 'statement_balance_pence', 'ledger_total_pence',
                'unpresented_total_pence', 'unmatched_statement_total_pence', 'difference_pence',
                'notes', 'approved_at')}


def _audit_recon(db: Session, row: BankReconciliation, actor: User, action: str,
                 before: dict | None = None, reason: str | None = None) -> None:
    after = _recon_snapshot(row)
    if before is not None:
        after.pop('notes')  # Keep the full previous notes without duplicating up to 4,000 characters.
    log_event(db, actor_user_id=actor.id, action=f'bank.reconciliation.{action}',
        entity_type='bank_reconciliation', entity_id=str(row.id),
        meta={'before': before, 'after': after, 'reason': reason})


def _locked_recon(db: Session, row: BankReconciliation, actor: User, expected_version: int) -> BankReconciliation:
    require_banking(actor, db)
    lock_bank(db, row.firm_bank_account_id)
    db.refresh(row, with_for_update=True)
    if row.version != expected_version:
        raise HTTPException(409, 'This reconciliation changed. Refresh before continuing.')
    return row


def _refresh_totals(db: Session, row: BankReconciliation) -> None:
    totals = compute_recon_totals(db, firm_bank_account_id=row.firm_bank_account_id,
        statement_balance_pence=row.statement_balance_pence, period_end_date=row.period_end_date)
    for key, value in totals.items():
        setattr(row, key, value)


def refresh_bank_reconciliation(db: Session, row: BankReconciliation, *, actor: User, expected_version: int,
                                statement_balance_pence: int | None = None, notes: str | None = None) -> BankReconciliation:
    row = _locked_recon(db, row, actor, expected_version)
    if row.status == 'approved':
        raise HTTPException(409, 'Approved reconciliations must be reopened before correction')
    before = _recon_snapshot(row)
    if statement_balance_pence is not None:
        row.statement_balance_pence = statement_balance_pence
    if notes is not None:
        row.notes = notes.strip() or None
    _refresh_totals(db, row)
    row.version += 1
    db.flush()
    _audit_recon(db, row, actor, 'update', before)
    return row


def approve_bank_reconciliation(db: Session, *, actor: User, row: BankReconciliation,
                                expected_version: int) -> BankReconciliation:
    row = _locked_recon(db, row, actor, expected_version)
    if not user_may_approve_ledger(actor, db):
        raise HTTPException(403, 'Not permitted to approve reconciliations')
    if row.status == 'approved':
        return row
    before = _recon_snapshot(row)
    _refresh_totals(db, row)
    if row.difference_pence != 0 and not (row.notes or '').strip():
        raise HTTPException(400, 'Notes are required when the reconciliation difference is not zero')
    row.status = 'approved'
    row.approved_by_user_id = actor.id
    row.approved_at = datetime.now(timezone.utc)
    row.version += 1
    db.flush()
    _audit_recon(db, row, actor, 'approve', before)
    return row


def reopen_bank_reconciliation(db: Session, *, actor: User, row: BankReconciliation,
                               expected_version: int, reason: str) -> BankReconciliation:
    row = _locked_recon(db, row, actor, expected_version)
    if not user_may_approve_ledger(actor, db):
        raise HTTPException(403, 'Not permitted to reopen reconciliations')
    if not reason.strip():
        raise HTTPException(400, 'A correction reason is required')
    if row.status != 'approved':
        raise HTTPException(409, 'Only approved reconciliations can be reopened')
    before = _recon_snapshot(row)
    row.status = 'draft'
    row.approved_at = None
    row.approved_by_user_id = None
    row.version += 1
    db.flush()
    _audit_recon(db, row, actor, 'reopen', before, reason.strip())
    return row


def list_bank_reconciliations(db: Session, *, firm_bank_account_id: uuid.UUID | None = None) -> list[BankReconciliation]:
    q = select(BankReconciliation).order_by(BankReconciliation.period_end_date.desc()).limit(48)
    if firm_bank_account_id:
        q = q.where(BankReconciliation.firm_bank_account_id == firm_bank_account_id)
    return list(db.execute(q).scalars().all())

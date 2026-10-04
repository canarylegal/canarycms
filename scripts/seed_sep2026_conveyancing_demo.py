#!/usr/bin/env python3
"""Seed realistic Sep 2026 conveyancing ledger/invoice/reconcile data for accountant pack demos.

Idempotent via reference prefix DEMO-SEP26. Intended to run inside the backend container.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("FILES_ROOT", "/data/files")

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.invoice_service import approve_case_invoice, create_case_invoice
from app.ledger_service import post_transaction
from app.models import (
    Case,
    CaseInvoice,
    CaseStatus,
    ClientAccountReconciliation,
    LedgerAccount,
    LedgerEntry,
    MatterHeadType,
    MatterSubType,
    ReconciliationStatus,
    User,
)
from app.reconciliation_service import (
    approve_reconciliation,
    create_reconciliation,
    firm_wide_ledger_totals,
    get_reconciliation_for_period,
    update_reconciliation,
)
from app.schemas import CaseInvoiceCreate, CaseInvoiceLineCreate, LedgerPostCreate

REF = "DEMO-SEP26"
FE_ID = uuid.UUID("b3172e5c-d989-4d30-8622-2a21a27d0388")  # demo fee earner (local DB)
TZ = ZoneInfo("Europe/London")
PERIOD_END = date(2026, 9, 30)


def _dt(y: int, m: int, d: int, hh: int = 10, mm: int = 15) -> datetime:
    return datetime(y, m, d, hh, mm, 0, tzinfo=TZ).astimezone(timezone.utc)


def _already_seeded(db: Session) -> bool:
    n = db.execute(
        select(LedgerEntry.id).where(LedgerEntry.reference == REF).limit(1)
    ).scalar_one_or_none()
    return n is not None


def _client_balance(db: Session, case_id: uuid.UUID) -> int:
    row = db.execute(
        text(
            """
            SELECT coalesce(sum(
              CASE WHEN le.direction = 'credit' THEN le.amount_pence ELSE -le.amount_pence END
            ), 0)
            FROM ledger_entry le
            JOIN ledger_account la ON la.id = le.account_id
            WHERE la.case_id = :cid AND la.account_type = 'client' AND le.is_approved
            """
        ),
        {"cid": case_id},
    ).scalar()
    return int(row or 0)


def _post(
    db: Session,
    *,
    case_id: uuid.UUID,
    user: User,
    when: datetime,
    description: str,
    amount_pence: int,
    client_direction: str | None = None,
    office_direction: str | None = None,
    contact_label: str | None = None,
) -> uuid.UUID:
    result = post_transaction(
        case_id,
        LedgerPostCreate(
            description=description,
            reference=REF,
            contact_label=contact_label,
            amount_pence=amount_pence,
            client_direction=client_direction,  # type: ignore[arg-type]
            office_direction=office_direction,  # type: ignore[arg-type]
        ),
        user,
        db,
    )
    db.execute(
        update(LedgerEntry)
        .where(LedgerEntry.pair_id == result.pair_id)
        .values(posted_at=when)
    )
    db.flush()
    return result.pair_id


def _invoice(
    db: Session,
    *,
    case_id: uuid.UUID,
    user: User,
    when: datetime,
    fee_net: int,
    fee_label: str,
    disbursements: list[tuple[str, int]] | None = None,
) -> str:
    vat = int(round(fee_net * 0.20))
    lines = [
        CaseInvoiceLineCreate(
            line_type="fee",
            description=fee_label,
            amount_pence=fee_net,
            tax_pence=vat,
            credit_user_id=user.id,
        )
    ]
    for label, amt in disbursements or []:
        lines.append(
            CaseInvoiceLineCreate(
                line_type="disbursement",
                description=label,
                amount_pence=amt,
                tax_pence=0,
            )
        )
    out = create_case_invoice(
        case_id,
        CaseInvoiceCreate(credit_user_id=user.id, lines=lines),
        user,
        db,
    )
    approve_case_invoice(case_id, out.id, user, db)
    inv = db.get(CaseInvoice, out.id)
    assert inv is not None
    inv.created_at = when
    inv.approved_at = when
    db.add(inv)
    if inv.ledger_pair_id:
        db.execute(
            update(LedgerEntry)
            .where(LedgerEntry.pair_id == inv.ledger_pair_id)
            .values(posted_at=when, reference=REF)
        )
    db.flush()
    return inv.invoice_number


def _pick_matters(db: Session) -> list[Case]:
    """Prefer Colin's open conveyancing matters with healthy client balances."""
    rows = db.execute(
        select(Case, MatterSubType.name)
        .join(MatterSubType, MatterSubType.id == Case.matter_sub_type_id)
        .join(MatterHeadType, MatterHeadType.id == MatterSubType.head_type_id)
        .where(
            Case.fee_earner_user_id == FE_ID,
            Case.status == CaseStatus.open,
            MatterHeadType.name.ilike("%convey%"),
        )
        .order_by(MatterSubType.name, Case.case_number)
    ).all()

    by_type: dict[str, list[Case]] = {}
    for case, subtype in rows:
        bal = _client_balance(db, case.id)
        if bal < 50_000:  # need room for fee transfers / completions
            continue
        by_type.setdefault(subtype, []).append(case)

    picks: list[Case] = []
    # Aim for a small-firm mix across subtypes
    want = [
        ("Purchase", 4),
        ("Sale", 3),
        ("Remortgage", 2),
        ("Refinance", 1),
        ("Transfer", 1),
        ("General", 1),
    ]
    for subtype, n in want:
        for c in by_type.get(subtype, [])[:n]:
            picks.append(c)
    return picks


def seed(db: Session) -> dict:
    if _already_seeded(db):
        return {"skipped": True, "reason": f"reference {REF} already present"}

    user = db.execute(select(User).where(User.id == FE_ID)).scalar_one()
    matters = _pick_matters(db)
    if len(matters) < 8:
        raise RuntimeError(f"Expected >=8 conveyancing matters with balance; got {len(matters)}")

    stats = {
        "matters": len(matters),
        "posts": 0,
        "invoices": 0,
        "case_numbers": [c.case_number for c in matters],
    }

    # Matter-specific realistic timelines spread across September
    scenarios: list[list[tuple]] = [
        # Purchase — mid-chain, searches + deposit + fee invoice + part transfer
        [
            ("recv", 2, 11, 0, "Client payment on account — search pack", 175_000, None),
            ("office", 3, 14, 30, "Local authority search", 18_500, None),
            ("office", 3, 14, 45, "Water and drainage search", 7_800, None),
            ("office", 4, 9, 20, "Environmental search", 12_400, None),
            ("office", 4, 9, 35, "Land Registry official copy", 7_00, None),
            ("office", 5, 10, 0, "AML identity check fee", 25_00, None),
            ("inv", 12, 16, 0, None, None, ("Professional fees — purchase (interim)", 95_000, [("Bank TT fee", 3_500)])),
            ("xfer", 12, 16, 30, "Transfer to office — professional fees", 117_500, None),  # 95000+19000+3500
            ("recv", 18, 10, 0, "Further client payment — SDLT on account", 450_000, None),
        ],
        # Purchase — near completion
        [
            ("recv", 1, 9, 30, "Initial deposit received", 250_000, None),
            ("office", 5, 11, 0, "Local authority search", 16_200, None),
            ("office", 5, 11, 15, "Coal mining search", 8_900, None),
            ("office", 8, 15, 0, "Land Registry official copy", 7_00, None),
            ("recv", 22, 11, 0, "Completion funds received", 18_500_000, None),
            ("client", 24, 14, 0, "Telegraphic transfer to vendor solicitors", 18_200_000, None),
            ("inv", 25, 10, 0, None, None, ("Professional fees — purchase completion", 125_000, [])),
            ("xfer", 25, 10, 20, "Bill payment from client account", 150_000, None),
            ("xfer", 25, 10, 40, "Transfer to office — completion fee", 35_000, None),
        ],
        # Purchase — early instructions
        [
            ("recv", 8, 10, 0, "Client payment on account", 150_000, None),
            ("office", 9, 11, 0, "AML identity check fee", 25_00, None),
            ("office", 15, 9, 30, "Local authority search", 17_800, None),
            ("office", 15, 9, 45, "Water and drainage search", 7_200, None),
            ("office", 16, 14, 0, "Environmental search", 11_900, None),
            ("inv", 29, 15, 0, None, None, ("Professional fees — purchase (stage 1)", 75_000, [])),
            ("xfer", 29, 15, 30, "Transfer to office — professional fees", 90_000, None),
        ],
        # Purchase — mortgage instructions / lender panel
        [
            ("recv", 4, 12, 0, "Client payment on account — lender work", 200_000, None),
            ("office", 10, 10, 0, "Land Registry official copy", 14_00, None),
            ("office", 11, 11, 0, "Bankruptcy search", 4_80, None),
            ("office", 17, 13, 0, "Local authority search", 15_600, None),
            ("inv", 23, 11, 0, None, None, ("Professional fees — purchase / mortgage", 110_000, [("OS1 priority search", 5_00)])),
            ("xfer", 23, 11, 30, "Bill payment from client account", 132_500, None),
        ],
        # Sale — exchanged
        [
            ("recv", 3, 10, 0, "Client payment on account", 100_000, None),
            ("office", 6, 9, 0, "Land Registry official copy", 7_00, None),
            ("office", 6, 9, 15, "AML identity check fee", 25_00, None),
            ("inv", 14, 16, 0, None, None, ("Professional fees — sale (exchange)", 85_000, [])),
            ("xfer", 14, 16, 20, "Transfer to office — professional fees", 102_000, None),
            ("recv", 26, 12, 0, "Completion funds received from purchaser solicitors", 24_750_000, None),
            ("client", 26, 15, 0, "Telegraphic transfer to client — net proceeds", 24_400_000, None),
            ("xfer", 26, 15, 30, "Transfer to office — completion fee", 45_000, None),
        ],
        # Sale — pre-exchange
        [
            ("recv", 7, 11, 0, "Client payment on account", 120_000, None),
            ("office", 9, 10, 0, "AML identity check fee", 25_00, None),
            ("office", 18, 14, 0, "Land Registry official copy", 14_00, None),
            ("inv", 28, 10, 0, None, None, ("Professional fees — sale (instructions)", 65_000, [])),
            ("xfer", 28, 10, 30, "Transfer to office — professional fees", 78_000, None),
        ],
        # Sale — chain completion
        [
            ("recv", 11, 9, 0, "Further client payment", 80_000, None),
            ("office", 12, 11, 0, "Bank transfer charge", 25_00, None),
            ("recv", 19, 13, 0, "Completion funds received", 31_200_000, None),
            ("client", 19, 15, 30, "Telegraphic transfer to redeem mortgage", 18_450_000, None),
            ("client", 19, 16, 0, "Telegraphic transfer to client — balance proceeds", 12_400_000, None),
            ("inv", 20, 10, 0, None, None, ("Professional fees — sale completion", 145_000, [("Telegraphic transfer fee", 4_500)])),
            ("xfer", 20, 10, 30, "Bill payment from client account", 178_500, None),
        ],
        # Remortgage
        [
            ("recv", 5, 10, 0, "Client payment on account — remortgage", 175_000, None),
            ("office", 8, 11, 0, "Land Registry official copy", 7_00, None),
            ("office", 8, 11, 15, "AML identity check fee", 25_00, None),
            ("office", 15, 9, 0, "Bankruptcy search", 4_80, None),
            ("inv", 21, 14, 0, None, None, ("Professional fees — remortgage", 95_000, [])),
            ("xfer", 21, 14, 30, "Transfer to office — professional fees", 114_000, None),
            ("recv", 29, 11, 0, "Advance funds received from new lender", 22_000_000, None),
            ("client", 29, 14, 0, "Telegraphic transfer to redeem existing mortgage", 21_650_000, None),
        ],
        # Remortgage — lighter
        [
            ("recv", 9, 10, 0, "Client payment on account", 140_000, None),
            ("office", 10, 11, 0, "AML identity check fee", 25_00, None),
            ("office", 16, 10, 0, "Land Registry official copy", 7_00, None),
            ("inv", 27, 15, 0, None, None, ("Professional fees — remortgage", 75_000, [])),
            ("xfer", 27, 15, 30, "Bill payment from client account", 90_000, None),
        ],
        # Refinance / Transfer / General (remaining matters)
        [
            ("recv", 2, 10, 0, "Client payment on account", 160_000, None),
            ("office", 4, 11, 0, "Local authority search", 15_200, None),
            ("office", 4, 11, 20, "Environmental search", 10_800, None),
            ("inv", 17, 12, 0, None, None, ("Professional fees — refinance", 105_000, [])),
            ("xfer", 17, 12, 30, "Transfer to office — professional fees", 126_000, None),
        ],
        [
            ("recv", 10, 9, 30, "Client payment on account — transfer of equity", 200_000, None),
            ("office", 11, 10, 0, "Land Registry official copy", 14_00, None),
            ("office", 11, 10, 15, "AML identity check fee", 25_00, None),
            ("inv", 24, 11, 0, None, None, ("Professional fees — transfer of equity", 85_000, [("SDLT return fee", 12_500)])),
            ("xfer", 24, 11, 30, "Bill payment from client account", 114_500, None),
        ],
        [
            ("recv", 6, 14, 0, "Client payment on account", 90_000, None),
            ("office", 13, 10, 0, "AML identity check fee", 25_00, None),
            ("office", 20, 11, 0, "Land Registry official copy", 7_00, None),
            ("inv", 30, 10, 0, None, None, ("Professional fees — conveyancing general", 55_000, [])),
            ("xfer", 30, 10, 30, "Transfer to office — professional fees", 66_000, None),
        ],
    ]

    for case, scenario in zip(matters, scenarios):
        client_name = (case.client_name or "Client").split(",")[0].strip()
        for step in scenario:
            kind = step[0]
            day, hh, mm = step[1], step[2], step[3]
            when = _dt(2026, 9, day, hh, mm)
            if kind == "recv":
                _post(
                    db,
                    case_id=case.id,
                    user=user,
                    when=when,
                    description=step[4],
                    amount_pence=step[5],
                    client_direction="credit",
                    contact_label=client_name,
                )
                stats["posts"] += 1
            elif kind == "office":
                _post(
                    db,
                    case_id=case.id,
                    user=user,
                    when=when,
                    description=step[4],
                    amount_pence=step[5],
                    office_direction="debit",
                )
                stats["posts"] += 1
            elif kind == "client":
                bal = _client_balance(db, case.id)
                amt = step[5]
                if amt > bal:
                    amt = max(bal - 10_000, 1)  # leave a small residual
                if amt <= 0:
                    continue
                _post(
                    db,
                    case_id=case.id,
                    user=user,
                    when=when,
                    description=step[4],
                    amount_pence=amt,
                    client_direction="debit",
                    contact_label=client_name,
                )
                stats["posts"] += 1
            elif kind == "xfer":
                bal = _client_balance(db, case.id)
                amt = step[5]
                if amt > bal:
                    amt = max(bal - 5_000, 1)
                if amt <= 0:
                    continue
                _post(
                    db,
                    case_id=case.id,
                    user=user,
                    when=when,
                    description=step[4],
                    amount_pence=amt,
                    client_direction="debit",
                    office_direction="credit",
                    contact_label=client_name,
                )
                stats["posts"] += 1
            elif kind == "inv":
                fee_label, fee_net, disbs = step[6]
                inv_num = _invoice(
                    db,
                    case_id=case.id,
                    user=user,
                    when=when,
                    fee_net=fee_net,
                    fee_label=fee_label,
                    disbursements=disbs,
                )
                stats["invoices"] += 1
                stats.setdefault("invoice_numbers", []).append(inv_num)

    # Month-end client account reconciliation (perfect bank match)
    client_total, _office = firm_wide_ledger_totals(db)
    existing = get_reconciliation_for_period(db, PERIOD_END)
    if existing is None:
        row = create_reconciliation(
            db,
            actor=user,
            period_end_date=PERIOD_END,
            bank_statement_balance_pence=client_total,
            notes="September 2026 month-end — DEMO-SEP26 seed (bank matches client ledger).",
        )
        approve_reconciliation(db, actor=user, row=row)
        stats["reconciliation"] = "created_approved"
    elif existing.status == ReconciliationStatus.draft:
        update_reconciliation(
            db,
            actor=user,
            row=existing,
            bank_statement_balance_pence=client_total,
            notes="September 2026 month-end — DEMO-SEP26 seed (bank matches client ledger).",
        )
        approve_reconciliation(db, actor=user, row=existing)
        stats["reconciliation"] = "updated_approved"
    else:
        stats["reconciliation"] = f"already_{existing.status.value}"
        stats["recon_diff"] = existing.difference_pence

    db.commit()
    stats["firm_client_total_pence"] = client_total
    return stats


def main() -> None:
    db = SessionLocal()
    try:
        result = seed(db)
        print(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

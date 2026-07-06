"""Client account reconciliation CRUD and report download."""

from __future__ import annotations

import os
import tempfile
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.docx_util import write_client_account_reconcile_report_docx
from app.download_headers import attachment_content_disposition_headers
from app.models import User
from app.permission_checks import user_may_approve_ledger
from app.reconciliation_service import (
    approve_reconciliation,
    create_reconciliation,
    firm_settings_for_report,
    firm_wide_ledger_totals,
    get_reconciliation,
    list_reconciliations,
    reconciliation_to_dict,
    update_reconciliation,
)
from app.schemas import (
    ClientAccountReconciliationCreateIn,
    ClientAccountReconciliationOut,
    ClientAccountReconciliationUpdateIn,
    ReconciliationPreviewOut,
)

router = APIRouter(prefix="/reports/reconciliations", tags=["reports-reconciliations"])


def _to_out(row, db: Session) -> ClientAccountReconciliationOut:
    return ClientAccountReconciliationOut.model_validate(reconciliation_to_dict(row, db))


@router.get("/preview-totals", response_model=ReconciliationPreviewOut)
def preview_totals(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReconciliationPreviewOut:
    del user
    client, office = firm_wide_ledger_totals(db)
    return ReconciliationPreviewOut(
        ledger_client_total_pence=client,
        ledger_office_total_pence=office,
    )


@router.get("", response_model=list[ClientAccountReconciliationOut])
def list_reconciliation_rows(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ClientAccountReconciliationOut]:
    del user
    rows = list_reconciliations(db)
    return [_to_out(r, db) for r in rows]


@router.get("/permissions")
def reconciliation_permissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"can_approve_reconciliation": user_may_approve_ledger(user, db)}


@router.get("/{rec_id}", response_model=ClientAccountReconciliationOut)
def get_reconciliation_row(
    rec_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientAccountReconciliationOut:
    del user
    row = get_reconciliation(db, rec_id)
    return _to_out(row, db)


@router.post("", response_model=ClientAccountReconciliationOut, status_code=status.HTTP_201_CREATED)
def post_reconciliation(
    body: ClientAccountReconciliationCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientAccountReconciliationOut:
    row = create_reconciliation(
        db,
        actor=user,
        period_end_date=body.period_end_date,
        bank_statement_balance_pence=body.bank_statement_balance_pence,
        notes=body.notes,
    )
    db.commit()
    db.refresh(row)
    return _to_out(row, db)


@router.patch("/{rec_id}", response_model=ClientAccountReconciliationOut)
def patch_reconciliation(
    rec_id: uuid.UUID,
    body: ClientAccountReconciliationUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientAccountReconciliationOut:
    row = get_reconciliation(db, rec_id)
    row = update_reconciliation(
        db,
        actor=user,
        row=row,
        bank_statement_balance_pence=body.bank_statement_balance_pence,
        notes=body.notes,
        refresh_ledger_totals=body.refresh_ledger_totals,
    )
    db.commit()
    db.refresh(row)
    return _to_out(row, db)


@router.post("/{rec_id}/approve", response_model=ClientAccountReconciliationOut)
def post_reconciliation_approve(
    rec_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientAccountReconciliationOut:
    row = get_reconciliation(db, rec_id)
    row = approve_reconciliation(db, actor=user, row=row)
    db.commit()
    db.refresh(row)
    return _to_out(row, db)


@router.get("/{rec_id}/report.docx")
def download_reconciliation_report(
    rec_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    del user
    row = get_reconciliation(db, rec_id)
    firm = firm_settings_for_report(db)
    prepared_name = reconciliation_to_dict(row, db).get("prepared_by_name")
    approved_name = reconciliation_to_dict(row, db).get("approved_by_name")

    fd, tmp_name = tempfile.mkstemp(suffix=".docx")
    tmp = Path(tmp_name)
    try:
        os.close(fd)
        write_client_account_reconcile_report_docx(
            tmp,
            firm_trading_name=firm.trading_name or "",
            firm_registered_name=firm.registered_company_name,
            client_bank_account_name=firm.client_bank_account_name,
            client_bank_sort_code=firm.client_bank_sort_code,
            client_bank_account_number_last4=firm.client_bank_account_number_last4,
            client_bank_account_number=firm.client_bank_account_number,
            period_end_date=row.period_end_date,
            ledger_client_total_pence=row.ledger_client_total_pence,
            ledger_office_total_pence=row.ledger_office_total_pence,
            bank_statement_balance_pence=row.bank_statement_balance_pence,
            difference_pence=row.difference_pence,
            prepared_by_name=prepared_name,
            prepared_at=row.prepared_at,
            approved_by_name=approved_name,
            approved_at=row.approved_at,
            notes=row.notes,
            status=row.status.value,
        )
        data = tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)

    period_label = row.period_end_date.strftime("%Y-%m")
    filename = f"Client account reconcile report — {period_label}.docx"
    bio = BytesIO(data)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=attachment_content_disposition_headers(filename),
    )

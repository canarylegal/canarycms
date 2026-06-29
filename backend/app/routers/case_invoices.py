"""Case invoice CRUD + approve + void + invoice document download."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.billing_service import invoice_billing_defaults_for_case
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.invoice_document_service import read_invoice_document_bytes
from app.invoice_service import (
    INV_APPROVED,
    approve_case_invoice,
    create_case_invoice,
    list_case_invoices,
    void_case_invoice,
)
from app.models import Case, CaseInvoice, User
from app.schemas import CaseInvoiceCreate, CaseInvoiceOut, CaseInvoicesOut, InvoiceBillingDefaultsOut, RejectCommentIn

router = APIRouter(prefix="/cases", tags=["case-invoices"])


@router.get("/{case_id}/invoice-billing-defaults", response_model=InvoiceBillingDefaultsOut)
def invoice_billing_defaults(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvoiceBillingDefaultsOut:
    require_case_access(case_id, user, db)
    return invoice_billing_defaults_for_case(case_id, db)


@router.get("/{case_id}/invoices", response_model=CaseInvoicesOut)
def read_invoices(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseInvoicesOut:
    require_case_access(case_id, user, db)
    return list_case_invoices(case_id, db)


@router.post("/{case_id}/invoices", response_model=CaseInvoiceOut, status_code=status.HTTP_201_CREATED)
def add_invoice(
    case_id: uuid.UUID,
    payload: CaseInvoiceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CaseInvoiceOut:
    require_case_access(case_id, user, db)
    out = create_case_invoice(case_id, payload, user, db)
    db.commit()
    return out


@router.post("/{case_id}/invoices/{invoice_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve_invoice(
    case_id: uuid.UUID,
    invoice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    approve_case_invoice(case_id, invoice_id, user, db)
    db.commit()


@router.get("/{case_id}/invoices/{invoice_id}/document.docx")
def download_invoice_document(
    case_id: uuid.UUID,
    invoice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    require_case_access(case_id, user, db)
    inv = db.get(CaseInvoice, invoice_id)
    if not inv or inv.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if inv.status != INV_APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice document is available only for approved invoices.",
        )
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    data, filename = read_invoice_document_bytes(inv, case, db)
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{case_id}/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    case_id: uuid.UUID,
    invoice_id: uuid.UUID,
    payload: RejectCommentIn = Body(default_factory=RejectCommentIn),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    require_case_access(case_id, user, db)
    void_case_invoice(case_id, invoice_id, user, db, reject_comment=payload.comment)
    db.commit()

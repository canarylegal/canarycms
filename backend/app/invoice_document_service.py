"""Generate invoice .docx files and save them on the matter."""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.docx_util import (
    build_merge_fields,
    ensure_docx_proofing_language_en_gb_bytes,
    invoice_line_merge_fields,
    merge_precedent_codes,
    strip_empty_invoice_table_rows,
    write_invoice_docx,
)
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root
from app.global_precedent_loader import load_global_precedent_docx_bytes
from app.models import Case, CaseInvoice, CaseInvoiceLine, Contact, File as DbFile, FileCategory, FirmSettings, User
from app.precedent_constants import INVOICE_TEMPLATE_PRECEDENT_REFERENCE

INVOICE_FOLDER_PATH = "Accounts/Invoices"


def _firm_settings(db: Session) -> FirmSettings:
    row = db.get(FirmSettings, 1)
    if row is None:
        row = FirmSettings(id=1)
        db.add(row)
        db.flush()
    return row


def _invoice_filename(invoice_number: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in invoice_number.strip())
    safe = safe.strip("-") or "invoice"
    return f"Invoice {safe}.docx"


def _bill_to_name(inv: CaseInvoice, db: Session) -> str | None:
    if inv.payee_name and inv.payee_name.strip():
        return inv.payee_name.strip()
    if inv.contact_id:
        contact = db.get(Contact, inv.contact_id)
        if contact:
            name = (contact.name or "").strip()
            if name:
                return name
    return None


def _fee_earner_name(case: Case, db: Session) -> str | None:
    u = db.get(User, case.fee_earner_user_id)
    if not u:
        return None
    return (u.display_name or u.email or "").strip() or None


def _invoice_date(inv: CaseInvoice) -> date:
    dt = inv.approved_at or inv.created_at
    if dt is None:
        return date.today()
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def _invoice_line_dicts(inv: CaseInvoice, db: Session) -> list[dict[str, object]]:
    lines = (
        db.execute(select(CaseInvoiceLine).where(CaseInvoiceLine.invoice_id == inv.id).order_by(CaseInvoiceLine.id))
        .scalars()
        .all()
    )
    return [
        {
            "line_type": ln.line_type,
            "description": ln.description,
            "amount_pence": int(ln.amount_pence),
            "tax_pence": int(ln.tax_pence),
        }
        for ln in lines
    ]


def _build_invoice_from_precedent(
    inv: CaseInvoice,
    case: Case,
    firm: FirmSettings,
    db: Session,
    *,
    line_dicts: list[dict[str, object]],
) -> bytes | None:
    template_bytes = load_global_precedent_docx_bytes(db, INVOICE_TEMPLATE_PRECEDENT_REFERENCE)
    if template_bytes is None:
        return None
    fe_name = _fee_earner_name(case, db) or ""
    inv_date = _invoice_date(inv)
    bill_to = _bill_to_name(inv, db)
    fields = build_merge_fields(
        case,
        fee_earner_name=fe_name,
        merge_date=inv_date,
        firm=firm,
    )
    fields.update(
        invoice_line_merge_fields(
            invoice_number=inv.invoice_number,
            invoice_date=inv_date,
            bill_to_name=bill_to,
            lines=line_dicts,
            total_pence=int(inv.total_pence),
        )
    )
    docx_bytes = merge_precedent_codes(template_bytes, fields)
    docx_bytes = strip_empty_invoice_table_rows(docx_bytes)
    return ensure_docx_proofing_language_en_gb_bytes(docx_bytes)


def _build_default_invoice_docx_bytes(
    inv: CaseInvoice,
    case: Case,
    firm: FirmSettings,
    db: Session,
    *,
    line_dicts: list[dict[str, object]],
) -> bytes:
    fd, tmp_name = tempfile.mkstemp(suffix=".docx")
    tmp = Path(tmp_name)
    try:
        os.close(fd)
        write_invoice_docx(
            tmp,
            firm_trading_name=firm.trading_name or "",
            firm_registered_name=firm.registered_company_name,
            firm_addr_line1=firm.addr_line1,
            firm_addr_line2=firm.addr_line2,
            firm_town_city=firm.town_city,
            firm_county=firm.county,
            firm_postcode=firm.postcode,
            invoice_number=inv.invoice_number,
            invoice_date=_invoice_date(inv),
            case_number=case.case_number,
            client_name=case.client_name,
            matter_description=case.title,
            fee_earner_name=_fee_earner_name(case, db),
            bill_to_name=_bill_to_name(inv, db),
            lines=line_dicts,
            total_pence=int(inv.total_pence),
        )
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def build_invoice_docx_bytes(inv: CaseInvoice, case: Case, firm: FirmSettings, db: Session) -> bytes:
    line_dicts = _invoice_line_dicts(inv, db)
    from_precedent = _build_invoice_from_precedent(inv, case, firm, db, line_dicts=line_dicts)
    if from_precedent is not None:
        return from_precedent
    return _build_default_invoice_docx_bytes(inv, case, firm, db, line_dicts=line_dicts)


def save_invoice_document_to_case(
    *,
    inv: CaseInvoice,
    case: Case,
    actor_user_id: uuid.UUID,
    db: Session,
) -> uuid.UUID:
    """Write invoice .docx to Accounts/Invoices and link on the invoice row."""
    ensure_files_root()
    firm = _firm_settings(db)
    src_bytes = build_invoice_docx_bytes(inv, case, firm, db)
    orig = _invoice_filename(inv.invoice_number)
    file_id = uuid.uuid4()
    paths = case_file_paths(
        case_id=case.id,
        file_id=file_id,
        original_filename=orig,
        folder_path=INVOICE_FOLDER_PATH,
    )
    paths.abs_path.write_bytes(src_bytes)
    now = datetime.now(timezone.utc)
    row = DbFile(
        id=file_id,
        case_id=case.id,
        owner_id=actor_user_id,
        category=FileCategory.case_document,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        parent_file_id=None,
        source_imap_mbox=None,
        source_imap_uid=None,
        is_pinned=False,
        original_filename=orig,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=len(src_bytes),
        version=1,
        checksum=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    inv.document_file_id = file_id
    db.add(inv)
    db.flush()
    return file_id


def read_invoice_document_bytes(inv: CaseInvoice, case: Case, db: Session) -> tuple[bytes, str]:
    """Return (bytes, download_filename). Regenerates if no saved file."""
    filename = _invoice_filename(inv.invoice_number)
    if inv.document_file_id:
        row = db.get(DbFile, inv.document_file_id)
        if row and row.case_id == case.id and row.storage_path:
            path = (FILES_ROOT / row.storage_path).resolve()
            if str(path).startswith(str(FILES_ROOT)) and path.is_file():
                return path.read_bytes(), row.original_filename or filename
    firm = _firm_settings(db)
    return build_invoice_docx_bytes(inv, case, firm, db), filename

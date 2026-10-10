"""Staff: bank statement import, match, line recon, EOM, journals, Xero export."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import bank_recon_service as recon
from app.bank_accounts_service import list_bank_accounts
from app.client_account_eom_service import create_or_replace_eom, get_eom, list_eoms
from app.db import get_db
from app.deps import get_current_user
from app.inter_matter_journal_service import create_inter_matter_journal, list_inter_matter_journals
from app.models import User
from app.permission_checks import user_may_access_accounts_workspace
from app.schemas.bank import (
    BankReconciliationCreate,
    BankReconciliationOut,
    BankReconciliationUpdate,
    BankStatementImportOut,
    BankStatementLineOut,
    BankStatementMatchIn,
    ClientAccountEomCreate,
    ClientAccountEomOut,
    FirmBankAccountOut,
    InterMatterJournalCreate,
    InterMatterJournalOut,
    UnpresentedLedgerLegOut,
    XeroExportCreate,
    XeroExportOut,
    XeroSettingsOut,
    XeroSettingsUpdate,
)
from app.xero_export_service import (
    create_xero_export,
    get_xero_export,
    get_xero_settings,
    list_xero_exports,
    update_xero_settings,
)
from fastapi import HTTPException, status

router = APIRouter(prefix="/accounts/banking", tags=["banking"])


def _require_accounts(user: User, db: Session) -> None:
    if not user_may_access_accounts_workspace(user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accounts workspace required")


def _bank_out(row) -> FirmBankAccountOut:
    return FirmBankAccountOut(
        id=row.id,
        name=row.name,
        account_kind=row.account_kind,  # type: ignore[arg-type]
        sort_code=row.sort_code,
        account_number=row.account_number,
        account_number_last4=row.account_number_last4,
        is_active=row.is_active,
        is_default=row.is_default,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _line_out(row) -> BankStatementLineOut:
    return BankStatementLineOut(
        id=row.id,
        import_id=row.import_id,
        firm_bank_account_id=row.firm_bank_account_id,
        statement_date=row.statement_date,
        amount_pence=row.amount_pence,
        description=row.description,
        reference=row.reference,
        balance_pence=row.balance_pence,
        matched_pair_id=row.matched_pair_id,
        matched_at=row.matched_at,
        ignored=row.ignored,
    )


def _recon_out(row) -> BankReconciliationOut:
    return BankReconciliationOut(
        id=row.id,
        firm_bank_account_id=row.firm_bank_account_id,
        period_end_date=row.period_end_date,
        statement_balance_pence=row.statement_balance_pence,
        ledger_total_pence=row.ledger_total_pence,
        unpresented_total_pence=row.unpresented_total_pence,
        unmatched_statement_total_pence=row.unmatched_statement_total_pence,
        difference_pence=row.difference_pence,
        status=row.status,
        notes=row.notes,
        prepared_at=row.prepared_at,
        approved_at=row.approved_at,
    )


@router.get("/bank-accounts", response_model=list[FirmBankAccountOut])
def staff_list_bank_accounts(
    kind: str | None = "client",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FirmBankAccountOut]:
    # Available to any authenticated staff for ledger posting; full recon UI still gated.
    _ = user
    return [_bank_out(r) for r in list_bank_accounts(db, kind=kind, active_only=True)]


@router.post("/statements/import", response_model=BankStatementImportOut)
async def import_bank_statement(
    firm_bank_account_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BankStatementImportOut:
    _require_accounts(user, db)
    content = await file.read()
    imp = recon.import_statement(
        db,
        firm_bank_account_id=firm_bank_account_id,
        filename=file.filename,
        content=content,
        actor=user,
    )
    db.commit()
    lines = recon.list_statement_lines(db, firm_bank_account_id=firm_bank_account_id, unmatched_only=False)
    # Only return lines from this import
    from_import = [l for l in lines if l.import_id == imp.id]
    return BankStatementImportOut(
        id=imp.id,
        firm_bank_account_id=imp.firm_bank_account_id,
        filename=imp.filename,
        imported_at=imp.imported_at,
        line_count=imp.line_count,
        lines=[_line_out(l) for l in from_import],
    )


@router.get("/statements/lines", response_model=list[BankStatementLineOut])
def list_lines(
    firm_bank_account_id: uuid.UUID,
    unmatched_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BankStatementLineOut]:
    _require_accounts(user, db)
    return [
        _line_out(l)
        for l in recon.list_statement_lines(
            db, firm_bank_account_id=firm_bank_account_id, unmatched_only=unmatched_only
        )
    ]


@router.post("/statements/lines/{line_id}/match", response_model=BankStatementLineOut)
def match_statement_line(
    line_id: uuid.UUID,
    payload: BankStatementMatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BankStatementLineOut:
    _require_accounts(user, db)
    row = recon.match_line(db, line_id=line_id, ledger_pair_id=payload.ledger_pair_id, actor=user)
    db.commit()
    db.refresh(row)
    return _line_out(row)


@router.post("/statements/lines/{line_id}/unmatch", response_model=BankStatementLineOut)
def unmatch_statement_line(
    line_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BankStatementLineOut:
    _require_accounts(user, db)
    row = recon.unmatch_line(db, line_id=line_id)
    db.commit()
    db.refresh(row)
    return _line_out(row)


@router.post("/statements/lines/{line_id}/ignore", response_model=BankStatementLineOut)
def ignore_statement_line(
    line_id: uuid.UUID,
    ignored: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BankStatementLineOut:
    _require_accounts(user, db)
    row = recon.ignore_line(db, line_id=line_id, ignored=ignored)
    db.commit()
    db.refresh(row)
    return _line_out(row)


@router.get("/unpresented", response_model=list[UnpresentedLedgerLegOut])
def list_unpresented(
    firm_bank_account_id: uuid.UUID,
    as_of: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UnpresentedLedgerLegOut]:
    _require_accounts(user, db)
    return [
        UnpresentedLedgerLegOut(**r)
        for r in recon.unpresented_client_legs(db, firm_bank_account_id=firm_bank_account_id, as_of=as_of)
    ]


@router.get("/reconciliations", response_model=list[BankReconciliationOut])
def list_recons(
    firm_bank_account_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BankReconciliationOut]:
    _require_accounts(user, db)
    return [_recon_out(r) for r in recon.list_bank_reconciliations(db, firm_bank_account_id=firm_bank_account_id)]


@router.post("/reconciliations", response_model=BankReconciliationOut)
def create_recon(
    payload: BankReconciliationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BankReconciliationOut:
    _require_accounts(user, db)
    row = recon.create_bank_reconciliation(
        db,
        actor=user,
        firm_bank_account_id=payload.firm_bank_account_id,
        period_end_date=payload.period_end_date,
        statement_balance_pence=payload.statement_balance_pence,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(row)
    return _recon_out(row)


@router.patch("/reconciliations/{rec_id}", response_model=BankReconciliationOut)
def update_recon(
    rec_id: uuid.UUID,
    payload: BankReconciliationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BankReconciliationOut:
    _require_accounts(user, db)
    from app.models import BankReconciliation

    row = db.get(BankReconciliation, rec_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    if payload.statement_balance_pence is not None:
        row.statement_balance_pence = payload.statement_balance_pence
    if payload.notes is not None:
        row.notes = payload.notes
    row = recon.refresh_bank_reconciliation(db, row)
    db.commit()
    db.refresh(row)
    return _recon_out(row)


@router.post("/reconciliations/{rec_id}/approve", response_model=BankReconciliationOut)
def approve_recon(
    rec_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BankReconciliationOut:
    _require_accounts(user, db)
    from app.models import BankReconciliation

    row = db.get(BankReconciliation, rec_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    row = recon.approve_bank_reconciliation(db, actor=user, row=row)
    db.commit()
    db.refresh(row)
    return _recon_out(row)


@router.get("/eom", response_model=list[ClientAccountEomOut])
def eom_list(
    firm_bank_account_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ClientAccountEomOut]:
    _require_accounts(user, db)
    return [
        ClientAccountEomOut(
            id=r.id,
            firm_bank_account_id=r.firm_bank_account_id,
            period_end_date=r.period_end_date,
            generated_at=r.generated_at,
            filename=r.filename,
            notes=r.notes,
        )
        for r in list_eoms(db, firm_bank_account_id=firm_bank_account_id)
    ]


@router.post("/eom", response_model=ClientAccountEomOut)
def eom_create(
    payload: ClientAccountEomCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientAccountEomOut:
    _require_accounts(user, db)
    row = create_or_replace_eom(
        db,
        actor=user,
        firm_bank_account_id=payload.firm_bank_account_id,
        period_end_date=payload.period_end_date,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(row)
    return ClientAccountEomOut(
        id=row.id,
        firm_bank_account_id=row.firm_bank_account_id,
        period_end_date=row.period_end_date,
        generated_at=row.generated_at,
        filename=row.filename,
        notes=row.notes,
    )


@router.get("/eom/{eom_id}/download")
def eom_download(
    eom_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    _require_accounts(user, db)
    row = get_eom(db, eom_id)
    return Response(
        content=row.content,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )


@router.get("/journals", response_model=list[InterMatterJournalOut])
def journals_list(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InterMatterJournalOut]:
    _require_accounts(user, db)
    return list_inter_matter_journals(db)


@router.post("/journals", response_model=InterMatterJournalOut)
def journals_create(
    payload: InterMatterJournalCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterMatterJournalOut:
    _require_accounts(user, db)
    out = create_inter_matter_journal(db, payload=payload, user=user)
    db.commit()
    return out


@router.get("/xero/settings", response_model=XeroSettingsOut)
def xero_settings_get(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> XeroSettingsOut:
    _require_accounts(user, db)
    s = get_xero_settings(db)
    return XeroSettingsOut(
        enabled=s.enabled,
        tenant_name=s.tenant_name,
        office_income_code=s.office_income_code,
        office_bank_code=s.office_bank_code,
        vat_code=s.vat_code,
        disbursement_code=s.disbursement_code,
    )


@router.put("/xero/settings", response_model=XeroSettingsOut)
def xero_settings_put(
    payload: XeroSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> XeroSettingsOut:
    _require_accounts(user, db)
    s = update_xero_settings(db, **payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(s)
    return XeroSettingsOut(
        enabled=s.enabled,
        tenant_name=s.tenant_name,
        office_income_code=s.office_income_code,
        office_bank_code=s.office_bank_code,
        vat_code=s.vat_code,
        disbursement_code=s.disbursement_code,
    )


@router.get("/xero/exports", response_model=list[XeroExportOut])
def xero_exports_list(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[XeroExportOut]:
    _require_accounts(user, db)
    return [
        XeroExportOut(
            id=r.id,
            period_from=r.period_from,
            period_to=r.period_to,
            generated_at=r.generated_at,
            filename=r.filename,
            row_count=r.row_count,
        )
        for r in list_xero_exports(db)
    ]


@router.post("/xero/exports", response_model=XeroExportOut)
def xero_exports_create(
    payload: XeroExportCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> XeroExportOut:
    _require_accounts(user, db)
    row = create_xero_export(
        db, actor=user, period_from=payload.period_from, period_to=payload.period_to
    )
    db.commit()
    db.refresh(row)
    return XeroExportOut(
        id=row.id,
        period_from=row.period_from,
        period_to=row.period_to,
        generated_at=row.generated_at,
        filename=row.filename,
        row_count=row.row_count,
    )


@router.get("/xero/exports/{export_id}/download")
def xero_export_download(
    export_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    _require_accounts(user, db)
    row = get_xero_export(db, export_id)
    return Response(
        content=row.content,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )

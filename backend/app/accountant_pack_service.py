"""Accountant export pack: multi-sheet workbook + optional reconcile report in a ZIP."""

from __future__ import annotations

import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.xlsx_util import autofit_workbook
from app.docx_util import write_client_account_reconcile_report_docx
from app.models import ClientAccountReconciliation, LedgerAccountType, ReconciliationStatus, User
from app.reconciliation_service import firm_settings_for_report, get_reconciliation_for_period, reconciliation_to_dict
from app.reports_service import (
    ExceptionsReport,
    LedgerLegActivityRow,
    pence_to_pounds_str,
    report_aged_debt,
    report_billing,
    report_client_office_balances,
    report_exceptions,
    report_ledger_leg_activity,
)


def activity_date_range(
    period_end_date: date,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    if date_from is None and date_to is None:
        return date(period_end_date.year, period_end_date.month, 1), period_end_date
    if date_from is None or date_to is None:
        raise ValueError("Provide both activity date_from and date_to, or leave both empty.")
    if date_from > date_to:
        raise ValueError("date_from must be on or before date_to.")
    return date_from, date_to


def _fee_earner_labels(db: Session, fee_earner_user_ids: list[uuid.UUID]) -> list[str]:
    labels: list[str] = []
    for uid in fee_earner_user_ids:
        u = db.get(User, uid)
        if u:
            labels.append((u.display_name or u.email or str(uid)).strip())
    return labels


@dataclass
class AccountantPackSectionPreview:
    key: str
    label: str
    included: bool
    row_count: int | None
    note: str | None


@dataclass
class AccountantPackPreview:
    period_end_date: date
    activity_date_from: date
    activity_date_to: date
    fee_earner_count: int
    reconcile_doc_available: bool
    sections: list[AccountantPackSectionPreview]


@dataclass
class AccountantPackBuildResult:
    zip_bytes: bytes
    filename: str
    preview: AccountantPackPreview


def _invoice_status_label(s: str) -> str:
    if s == "pending_approval":
        return "Pending approval"
    if s == "approved":
        return "Approved"
    if s == "voided":
        return "Voided"
    return s


def preview_accountant_pack(
    db: Session,
    *,
    fee_earner_user_ids: list[uuid.UUID],
    period_end_date: date,
    date_from: date | None,
    date_to: date | None,
    include_balances: bool,
    include_billing: bool,
    include_ledger_activity: bool,
    include_aged_debt: bool,
    include_exceptions: bool,
    include_reconcile_doc: bool,
    large_posting_min_pence: int,
) -> AccountantPackPreview:
    act_from, act_to = activity_date_range(period_end_date, date_from, date_to)
    sections: list[AccountantPackSectionPreview] = []

    if include_balances:
        rows, _totals = report_client_office_balances(fee_earner_user_ids, db)
        sections.append(
            AccountantPackSectionPreview("balances", "Client & office balances", True, len(rows), None)
        )

    if include_billing:
        rows, _totals = report_billing(
            fee_earner_user_ids, db, date_from=act_from, date_to=act_to
        )
        sections.append(
            AccountantPackSectionPreview("billing", "Billing", True, len(rows), None)
        )

    if include_ledger_activity:
        client_rows = report_ledger_leg_activity(
            fee_earner_user_ids,
            db,
            account_type=LedgerAccountType.client,
            date_from=act_from,
            date_to=act_to,
            approved_only=False,
        )
        office_rows = report_ledger_leg_activity(
            fee_earner_user_ids,
            db,
            account_type=LedgerAccountType.office,
            date_from=act_from,
            date_to=act_to,
            approved_only=False,
        )
        sections.append(
            AccountantPackSectionPreview(
                "client_ledger_activity", "Client ledger activity", True, len(client_rows), None
            )
        )
        sections.append(
            AccountantPackSectionPreview(
                "office_ledger_activity", "Office ledger activity", True, len(office_rows), None
            )
        )

    if include_aged_debt:
        rows, _bucket = report_aged_debt(fee_earner_user_ids, db, as_of=period_end_date)
        sections.append(
            AccountantPackSectionPreview("aged_debt", "Aged debt", True, len(rows), None)
        )

    if include_exceptions:
        report = report_exceptions(
            fee_earner_user_ids,
            db,
            date_from=act_from,
            date_to=act_to,
            large_posting_min_pence=large_posting_min_pence,
        )
        total = (
            len(report.pending_ledger_approvals)
            + len(report.pending_invoices)
            + len(report.client_balance_closed_archived)
            + len(report.negative_client_balance)
            + len(report.large_postings)
        )
        sections.append(
            AccountantPackSectionPreview("exceptions", "Exceptions", True, total, None)
        )

    rec = get_reconciliation_for_period(db, period_end_date)
    reconcile_available = bool(rec and rec.status == ReconciliationStatus.approved)
    if include_reconcile_doc:
        note = None
        if reconcile_available:
            note = "Approved reconciliation — Word document will be included"
        elif rec and rec.status == ReconciliationStatus.draft:
            note = "Draft reconciliation only — approve to include Word document"
        else:
            note = "No reconciliation for this period — Word document omitted"
        sections.append(
            AccountantPackSectionPreview(
                "reconcile_doc",
                "Client account reconcile report",
                include_reconcile_doc,
                None,
                note,
            )
        )

    return AccountantPackPreview(
        period_end_date=period_end_date,
        activity_date_from=act_from,
        activity_date_to=act_to,
        fee_earner_count=len(fee_earner_user_ids),
        reconcile_doc_available=reconcile_available,
        sections=sections,
    )


def _add_sheet(wb: Any, title: str, headers: list[str], data_rows: list[list[Any]]) -> None:
    ws = wb.create_sheet(title[:31])
    ws.append(headers)
    for row in data_rows:
        ws.append(row)


_LEDGER_LEG_HEADERS = [
    "Posted (UTC)",
    "Reference",
    "Client",
    "Matter",
    "Fee earner",
    "Description",
    "Ledger ref",
    "Amount (£)",
    "Direction",
    "Approved",
    "Posted by",
    "Contact",
]


def _ledger_leg_sheet_rows(rows: list[LedgerLegActivityRow]) -> list[list[Any]]:
    return [
        [
            r.posted_at.strftime("%Y-%m-%d %H:%M"),
            r.case_number,
            r.client_name or "",
            r.matter_description,
            r.fee_earner_name,
            r.description,
            r.reference or "",
            float(pence_to_pounds_str(r.amount_pence)),
            r.direction,
            "Yes" if r.is_approved else "Pending",
            r.posted_by_name,
            r.contact_label or "",
        ]
        for r in rows
    ]


def _build_summary_sheet(
    wb: Any,
    *,
    firm_trading_name: str,
    period_end_date: date,
    activity_date_from: date,
    activity_date_to: date,
    fee_earner_labels: list[str],
    generated_by_name: str,
    preview: AccountantPackPreview,
) -> None:
    ws = wb.active
    ws.title = "Summary"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ws.append(["Accountant export pack"])
    ws.append(["Firm", firm_trading_name or ""])
    ws.append(["Period end (balances / aged debt)", period_end_date.isoformat()])
    ws.append(["Activity date from", activity_date_from.isoformat()])
    ws.append(["Activity date to", activity_date_to.isoformat()])
    ws.append(["Fee earners", str(len(fee_earner_labels))])
    ws.append(["Fee earner names", ", ".join(fee_earner_labels) if fee_earner_labels else ""])
    ws.append(["Generated at", now])
    ws.append(["Generated by", generated_by_name])
    ws.append([])
    ws.append(["Section", "Included", "Rows", "Notes"])
    for s in preview.sections:
        if s.key == "reconcile_doc":
            ws.append([s.label, "Yes" if s.included else "No", "", s.note or ""])
        else:
            ws.append([s.label, "Yes" if s.included else "No", s.row_count if s.row_count is not None else "", s.note or ""])


def _build_workbook(
    db: Session,
    *,
    fee_earner_user_ids: list[uuid.UUID],
    period_end_date: date,
    activity_date_from: date,
    activity_date_to: date,
    include_balances: bool,
    include_billing: bool,
    include_ledger_activity: bool,
    include_aged_debt: bool,
    include_exceptions: bool,
    large_posting_min_pence: int,
    firm_trading_name: str,
    generated_by_name: str,
    preview: AccountantPackPreview,
) -> Any:
    from openpyxl import Workbook

    wb = Workbook()
    _build_summary_sheet(
        wb,
        firm_trading_name=firm_trading_name,
        period_end_date=period_end_date,
        activity_date_from=activity_date_from,
        activity_date_to=activity_date_to,
        fee_earner_labels=_fee_earner_labels(db, fee_earner_user_ids),
        generated_by_name=generated_by_name,
        preview=preview,
    )

    if include_balances:
        rows, totals = report_client_office_balances(fee_earner_user_ids, db)
        data = [
            [
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.fee_earner_name,
                float(pence_to_pounds_str(r.client_balance_pence)),
                float(pence_to_pounds_str(r.office_balance_pence)),
            ]
            for r in rows
        ]
        data.append(
            [
                "",
                "",
                "",
                "Total",
                float(pence_to_pounds_str(totals["client_balance_pence"])),
                float(pence_to_pounds_str(totals["office_balance_pence"])),
            ]
        )
        _add_sheet(
            wb,
            "Client office balances",
            ["Reference", "Client", "Matter description", "Fee earner", "Client balance (£)", "Office balance (£)"],
            data,
        )

    if include_billing:
        rows, totals = report_billing(
            fee_earner_user_ids, db, date_from=activity_date_from, date_to=activity_date_to
        )
        data = [
            [
                r.case_number,
                r.client_name or "",
                r.invoice_number,
                _invoice_status_label(r.invoice_status),
                r.fee_earner_name,
                r.created_at.strftime("%Y-%m-%d %H:%M"),
                float(pence_to_pounds_str(r.fees_ex_vat_pence)),
                float(pence_to_pounds_str(r.vat_pence)),
                float(pence_to_pounds_str(r.disbursements_ex_vat_pence)),
            ]
            for r in rows
        ]
        data.append(
            [
                "",
                "",
                "",
                "",
                "TOTAL",
                "",
                float(pence_to_pounds_str(totals["fees_ex_vat_pence"])),
                float(pence_to_pounds_str(totals["vat_pence"])),
                float(pence_to_pounds_str(totals["disbursements_ex_vat_pence"])),
            ]
        )
        _add_sheet(
            wb,
            "Billing",
            [
                "Reference",
                "Client",
                "Invoice",
                "Status",
                "Fee earner",
                "Created (UTC)",
                "Fees ex VAT (£)",
                "VAT (£)",
                "Disbursements ex VAT (£)",
            ],
            data,
        )

    if include_ledger_activity:
        client_rows = report_ledger_leg_activity(
            fee_earner_user_ids,
            db,
            account_type=LedgerAccountType.client,
            date_from=activity_date_from,
            date_to=activity_date_to,
            approved_only=False,
        )
        office_rows = report_ledger_leg_activity(
            fee_earner_user_ids,
            db,
            account_type=LedgerAccountType.office,
            date_from=activity_date_from,
            date_to=activity_date_to,
            approved_only=False,
        )
        _add_sheet(
            wb,
            "Client ledger activity",
            _LEDGER_LEG_HEADERS,
            _ledger_leg_sheet_rows(client_rows),
        )
        _add_sheet(
            wb,
            "Office ledger activity",
            _LEDGER_LEG_HEADERS,
            _ledger_leg_sheet_rows(office_rows),
        )

    if include_aged_debt:
        rows, bucket_totals = report_aged_debt(fee_earner_user_ids, db, as_of=period_end_date)
        data = [
            [
                r.age_bucket,
                r.age_days,
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.fee_earner_name,
                r.invoice_number,
                r.approved_at.strftime("%Y-%m-%d %H:%M"),
                float(pence_to_pounds_str(r.invoice_total_pence)),
                float(pence_to_pounds_str(r.office_balance_pence)),
            ]
            for r in rows
        ]
        data.extend(
            [
                [],
                ["Bucket summary (invoice totals £)", "", "", "", "", "", "", "0-30", "31-60", "61-90", "90+"],
                [
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    float(pence_to_pounds_str(bucket_totals["0-30"])),
                    float(pence_to_pounds_str(bucket_totals["31-60"])),
                    float(pence_to_pounds_str(bucket_totals["61-90"])),
                    float(pence_to_pounds_str(bucket_totals["90+"])),
                ],
            ]
        )
        _add_sheet(
            wb,
            "Aged debt",
            [
                "Age bucket",
                "Days",
                "Reference",
                "Client",
                "Matter",
                "Fee earner",
                "Invoice",
                "Approved (UTC)",
                "Invoice total (£)",
                "Office balance (£)",
            ],
            data,
        )

    if include_exceptions:
        report = report_exceptions(
            fee_earner_user_ids,
            db,
            date_from=activity_date_from,
            date_to=activity_date_to,
            large_posting_min_pence=large_posting_min_pence,
        )
        _add_exceptions_sheets(wb, report)

    return wb


def _add_exceptions_sheets(wb: Any, report: ExceptionsReport) -> None:
    _add_sheet(
        wb,
        "Pending ledger",
        ["Posted (UTC)", "Reference", "Client", "Matter", "Fee earner", "Description", "Amount (£)", "Client leg", "Office leg", "Posted by"],
        [
            [
                r.posted_at.strftime("%Y-%m-%d %H:%M"),
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.fee_earner_name,
                r.description,
                float(pence_to_pounds_str(r.amount_pence)),
                r.client_direction or "",
                r.office_direction or "",
                r.posted_by_name,
            ]
            for r in report.pending_ledger_approvals
        ],
    )
    _add_sheet(
        wb,
        "Pending invoices",
        ["Created (UTC)", "Reference", "Client", "Matter", "Fee earner", "Invoice", "Total (£)"],
        [
            [
                r.created_at.strftime("%Y-%m-%d %H:%M"),
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.fee_earner_name,
                r.invoice_number,
                float(pence_to_pounds_str(r.total_pence)),
            ]
            for r in report.pending_invoices
        ],
    )
    _add_sheet(
        wb,
        "Closed archived client",
        ["Reference", "Client", "Matter", "Status", "Fee earner", "Client balance (£)", "Office balance (£)"],
        [
            [
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.status_label,
                r.fee_earner_name,
                float(pence_to_pounds_str(r.client_balance_pence)),
                float(pence_to_pounds_str(r.office_balance_pence)),
            ]
            for r in report.client_balance_closed_archived
        ],
    )
    _add_sheet(
        wb,
        "Negative client balance",
        ["Reference", "Client", "Matter", "Status", "Fee earner", "Client balance (£)", "Office balance (£)"],
        [
            [
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.status_label,
                r.fee_earner_name,
                float(pence_to_pounds_str(r.client_balance_pence)),
                float(pence_to_pounds_str(r.office_balance_pence)),
            ]
            for r in report.negative_client_balance
        ],
    )
    _add_sheet(
        wb,
        "Large postings",
        ["Posted (UTC)", "Reference", "Client", "Matter", "Fee earner", "Description", "Amount (£)", "Approved", "Posted by"],
        [
            [
                r.posted_at.strftime("%Y-%m-%d %H:%M"),
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.fee_earner_name,
                r.description,
                float(pence_to_pounds_str(r.amount_pence)),
                "Yes" if r.is_approved else "Pending",
                r.posted_by_name,
            ]
            for r in report.large_postings
        ],
    )


def _write_reconcile_docx(rec: ClientAccountReconciliation, db: Session) -> bytes:
    firm = firm_settings_for_report(db)
    rec_dict = reconciliation_to_dict(rec, db)
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
            period_end_date=rec.period_end_date,
            ledger_client_total_pence=rec.ledger_client_total_pence,
            ledger_office_total_pence=rec.ledger_office_total_pence,
            bank_statement_balance_pence=rec.bank_statement_balance_pence,
            difference_pence=rec.difference_pence,
            prepared_by_name=rec_dict.get("prepared_by_name"),
            prepared_at=rec.prepared_at,
            approved_by_name=rec_dict.get("approved_by_name"),
            approved_at=rec.approved_at,
            notes=rec.notes,
            status=rec.status.value,
        )
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def build_accountant_pack(
    db: Session,
    *,
    fee_earner_user_ids: list[uuid.UUID],
    period_end_date: date,
    date_from: date | None,
    date_to: date | None,
    include_balances: bool,
    include_billing: bool,
    include_ledger_activity: bool,
    include_aged_debt: bool,
    include_exceptions: bool,
    include_reconcile_doc: bool,
    large_posting_min_pence: int,
    generated_by_name: str,
) -> AccountantPackBuildResult:
    preview = preview_accountant_pack(
        db,
        fee_earner_user_ids=fee_earner_user_ids,
        period_end_date=period_end_date,
        date_from=date_from,
        date_to=date_to,
        include_balances=include_balances,
        include_billing=include_billing,
        include_ledger_activity=include_ledger_activity,
        include_aged_debt=include_aged_debt,
        include_exceptions=include_exceptions,
        include_reconcile_doc=include_reconcile_doc,
        large_posting_min_pence=large_posting_min_pence,
    )
    firm = firm_settings_for_report(db)
    wb = _build_workbook(
        db,
        fee_earner_user_ids=fee_earner_user_ids,
        period_end_date=period_end_date,
        activity_date_from=preview.activity_date_from,
        activity_date_to=preview.activity_date_to,
        include_balances=include_balances,
        include_billing=include_billing,
        include_ledger_activity=include_ledger_activity,
        include_aged_debt=include_aged_debt,
        include_exceptions=include_exceptions,
        large_posting_min_pence=large_posting_min_pence,
        firm_trading_name=firm.trading_name or "",
        generated_by_name=generated_by_name,
        preview=preview,
    )

    period_label = period_end_date.strftime("%Y-%m")
    xlsx_name = f"canary-accountant-pack-{period_label}.xlsx"
    zip_name = f"canary-accountant-pack-{period_label}.zip"
    docx_name = f"Client account reconcile report — {period_label}.docx"

    xlsx_bio = BytesIO()
    autofit_workbook(wb)
    wb.save(xlsx_bio)
    xlsx_bytes = xlsx_bio.getvalue()

    zip_bio = BytesIO()
    with zipfile.ZipFile(zip_bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(xlsx_name, xlsx_bytes)
        if include_reconcile_doc:
            rec = get_reconciliation_for_period(db, period_end_date)
            if rec and rec.status == ReconciliationStatus.approved:
                zf.writestr(docx_name, _write_reconcile_docx(rec, db))

    return AccountantPackBuildResult(
        zip_bytes=zip_bio.getvalue(),
        filename=zip_name,
        preview=preview,
    )

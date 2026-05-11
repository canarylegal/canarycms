"""Authenticated reporting endpoints (JSON + Excel)."""

from __future__ import annotations

from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import CaseStatus, User
from app.reports_service import (
    enforce_fee_earner_ids,
    list_fee_earner_pick_users,
    pence_to_pounds_str,
    report_billing,
    report_cases,
    report_cases_opened,
    report_client_office_balances,
    report_events,
)
from app.schemas import (
    BillingReportIn,
    CasesOpenedReportIn,
    CasesReportIn,
    EventsReportIn,
    FeeEarnerPickOut,
    ReportFeeEarnerIdsIn,
)

router = APIRouter(prefix="/reports", tags=["reports"])

ReportFormat = Literal["json", "xlsx"]


def _wb_response(wb: Workbook, download_name: str) -> StreamingResponse:
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


def _invoice_status_label(s: str) -> str:
    if s == "pending_approval":
        return "Pending approval"
    if s == "approved":
        return "Approved"
    if s == "voided":
        return "Voided"
    return s


@router.get("/fee-earners", response_model=list[FeeEarnerPickOut])
def fee_earner_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[FeeEarnerPickOut]:
    rows = list_fee_earner_pick_users(user, db)
    return [FeeEarnerPickOut(id=u.id, display_name=u.display_name, email=u.email) for u in rows]


@router.post("/client-office-balances")
def post_client_office_balances(
    body: ReportFeeEarnerIdsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    format: Annotated[ReportFormat, Query()] = "json",
):
    ids = enforce_fee_earner_ids(user, db, body.fee_earner_user_ids)
    rows = report_client_office_balances(ids, db)
    if format == "json":
        return {
            "rows": [
                {
                    "case_id": str(r.case_id),
                    "case_number": r.case_number,
                    "client_name": r.client_name,
                    "matter_description": r.matter_description,
                    "fee_earner_name": r.fee_earner_name,
                    "client_balance_pence": r.client_balance_pence,
                    "office_balance_pence": r.office_balance_pence,
                }
                for r in rows
            ]
        }
    wb = Workbook()
    ws = wb.active
    ws.title = "Client office balances"
    ws.append(
        [
            "Reference",
            "Client",
            "Matter description",
            "Fee earner",
            "Client balance (£)",
            "Office balance (£)",
        ]
    )
    for r in rows:
        ws.append(
            [
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.fee_earner_name,
                float(pence_to_pounds_str(r.client_balance_pence)),
                float(pence_to_pounds_str(r.office_balance_pence)),
            ]
        )
    return _wb_response(wb, "canary-report-client-office-balances.xlsx")


@router.post("/billing")
def post_billing_report(
    body: BillingReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    format: Annotated[ReportFormat, Query()] = "json",
):
    ids = enforce_fee_earner_ids(user, db, body.fee_earner_user_ids)
    rows, totals = report_billing(ids, db, date_from=body.date_from, date_to=body.date_to)
    if format == "json":
        return {
            "rows": [
                {
                    "invoice_id": str(r.invoice_id),
                    "case_number": r.case_number,
                    "client_name": r.client_name,
                    "invoice_number": r.invoice_number,
                    "invoice_status": r.invoice_status,
                    "invoice_status_label": _invoice_status_label(r.invoice_status),
                    "fee_earner_name": r.fee_earner_name,
                    "created_at": r.created_at.isoformat(),
                    "fees_ex_vat_pence": r.fees_ex_vat_pence,
                    "vat_pence": r.vat_pence,
                    "disbursements_ex_vat_pence": r.disbursements_ex_vat_pence,
                }
                for r in rows
            ],
            "totals": totals,
        }
    wb = Workbook()
    ws = wb.active
    ws.title = "Billing"
    ws.append(
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
        ]
    )
    for r in rows:
        ws.append(
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
        )
    ws.append(
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
    return _wb_response(wb, "canary-report-billing.xlsx")


def _parse_case_statuses(raw: list[str] | None) -> list[CaseStatus] | None:
    if not raw:
        return None
    out: list[CaseStatus] = []
    for s in raw:
        try:
            out.append(CaseStatus(s))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid case status: {s!r}",
            ) from exc
    return out


@router.post("/cases")
def post_cases_report(
    body: CasesReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    format: Annotated[ReportFormat, Query()] = "json",
):
    ids = enforce_fee_earner_ids(user, db, body.fee_earner_user_ids)
    st = _parse_case_statuses(body.statuses)
    rows = report_cases(ids, db, statuses=st)
    if format == "json":
        return {
            "rows": [
                {
                    "case_id": str(r.case_id),
                    "case_number": r.case_number,
                    "client_name": r.client_name,
                    "matter_description": r.matter_description,
                    "status": r.status,
                    "status_label": r.status_label,
                    "fee_earner_name": r.fee_earner_name,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        }
    wb = Workbook()
    ws = wb.active
    ws.title = "Cases"
    ws.append(["Reference", "Client", "Matter description", "Status", "Fee earner", "Created (UTC)"])
    for r in rows:
        ws.append(
            [
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.status_label,
                r.fee_earner_name,
                r.created_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )
    return _wb_response(wb, "canary-report-cases.xlsx")


@router.post("/cases-opened")
def post_cases_opened_report(
    body: CasesOpenedReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    format: Annotated[ReportFormat, Query()] = "json",
):
    ids = enforce_fee_earner_ids(user, db, body.fee_earner_user_ids)
    rows = report_cases_opened(
        ids,
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        include_quote=body.include_quote,
        include_active=body.include_active,
    )
    if format == "json":
        return {
            "rows": [
                {
                    "case_id": str(r.case_id),
                    "case_number": r.case_number,
                    "client_name": r.client_name,
                    "matter_description": r.matter_description,
                    "status": r.status,
                    "status_label": r.status_label,
                    "fee_earner_name": r.fee_earner_name,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        }
    wb = Workbook()
    ws = wb.active
    ws.title = "Cases opened"
    ws.append(["Reference", "Client", "Matter description", "Status", "Fee earner", "Opened (UTC)"])
    for r in rows:
        ws.append(
            [
                r.case_number,
                r.client_name or "",
                r.matter_description,
                r.status_label,
                r.fee_earner_name,
                r.created_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )
    return _wb_response(wb, "canary-report-cases-opened.xlsx")


@router.post("/events")
def post_events_report(
    body: EventsReportIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    format: Annotated[ReportFormat, Query()] = "json",
):
    ids = enforce_fee_earner_ids(user, db, body.fee_earner_user_ids)
    rows = report_events(
        ids,
        db,
        date_from=body.date_from,
        date_to=body.date_to,
        template_ids=body.template_ids,
    )
    if format == "json":
        return {
            "rows": [
                {
                    "event_id": str(r.event_id),
                    "case_number": r.case_number,
                    "matter_description": r.matter_description,
                    "fee_earner_name": r.fee_earner_name,
                    "event_name": r.event_name,
                    "event_date": r.event_date.isoformat() if r.event_date else None,
                    "event_category": r.event_category or "",
                }
                for r in rows
            ]
        }
    wb = Workbook()
    ws = wb.active
    ws.title = "Events"
    ws.append(
        [
            "Event",
            "Event date",
            "Calendar template",
            "Reference",
            "Matter description",
            "Fee earner",
        ]
    )
    for r in rows:
        ws.append(
            [
                r.event_name,
                r.event_date.isoformat() if r.event_date else "",
                r.event_category or "",
                r.case_number,
                r.matter_description,
                r.fee_earner_name,
            ]
        )
    return _wb_response(wb, "canary-report-events.xlsx")

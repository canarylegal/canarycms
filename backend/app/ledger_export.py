"""Export a matter ledger to Excel (same columns as the All-accounts ledger view)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from openpyxl import Workbook

from app.models import Case
from app.reports_service import pence_to_pounds_str
from app.schemas import LedgerEntryOut, LedgerOut

_PENDING_SUFFIX = re.compile(r"\s*\(pending approval\)\s*", re.IGNORECASE)


def _entry_pending(entry: LedgerEntryOut) -> bool:
    if entry.is_approved is True:
        return False
    if entry.is_approved is False:
        return True
    return "(pending approval)" in (entry.description or "").lower()


def _description_display(entry: LedgerEntryOut) -> str:
    d = entry.description or ""
    if not _entry_pending(entry):
        d = _PENDING_SUFFIX.sub("", d).strip()
    return d


def _running_balances(entries: list[LedgerEntryOut]) -> dict[str, tuple[int | None, int | None]]:
    """Map entry id → (office_balance_pence, client_balance_pence); None when row is pending."""
    sorted_entries = sorted(entries, key=lambda e: e.posted_at)
    office = 0
    client = 0
    out: dict[str, tuple[int | None, int | None]] = {}
    for entry in sorted_entries:
        if _entry_pending(entry):
            out[str(entry.id)] = (None, None)
            continue
        delta = entry.amount_pence if entry.direction == "credit" else -entry.amount_pence
        if entry.account_type == "office":
            office += delta
        else:
            client += delta
        out[str(entry.id)] = (office, client)
    return out


def build_case_ledger_workbook(case: Case, ledger: LedgerOut) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ledger"

    ws.append(["Matter reference", case.case_number])
    ws.append(["Client", case.client_name or ""])
    ws.append(["Matter", case.title])
    ws.append(["Exported (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")])
    ws.append(["Client balance (approved)", float(pence_to_pounds_str(ledger.client.balance_pence))])
    ws.append(["Office balance (approved)", float(pence_to_pounds_str(ledger.office.balance_pence))])
    ws.append([])

    ws.append(
        [
            "Date",
            "Party",
            "Description",
            "Reference",
            "Office debit (£)",
            "Office credit (£)",
            "Client debit (£)",
            "Client credit (£)",
            "Office balance (£)",
            "Client balance (£)",
            "Status",
        ]
    )

    balances = _running_balances(ledger.entries)
    for entry in sorted(ledger.entries, key=lambda e: e.posted_at):
        office_bal, client_bal = balances.get(str(entry.id), (None, None))
        od = oc = cd = cc = ""
        if entry.account_type == "office":
            if entry.direction == "debit":
                od = pence_to_pounds_str(entry.amount_pence)
            else:
                oc = pence_to_pounds_str(entry.amount_pence)
        else:
            if entry.direction == "debit":
                cd = pence_to_pounds_str(entry.amount_pence)
            else:
                cc = pence_to_pounds_str(entry.amount_pence)
        ws.append(
            [
                entry.posted_at.strftime("%Y-%m-%d"),
                entry.contact_label or "",
                _description_display(entry),
                entry.reference or "",
                float(od) if od else "",
                float(oc) if oc else "",
                float(cd) if cd else "",
                float(cc) if cc else "",
                float(pence_to_pounds_str(office_bal)) if office_bal is not None else "",
                float(pence_to_pounds_str(client_bal)) if client_bal is not None else "",
                "Pending" if _entry_pending(entry) else "Approved",
            ]
        )
    return wb

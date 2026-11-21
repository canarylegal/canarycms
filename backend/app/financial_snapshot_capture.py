"""One PostgreSQL statement freezes report labels and source rows together."""

import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select, func, literal_column
from sqlalchemy.orm import aliased
from app.models import (
    BankReconciliation,
    BankStatementLine,
    Case,
    ClientAccountReconciliation,
    FirmBankAccount,
    FirmSettings,
    LedgerAccount,
    LedgerEntry,
    User,
)
from app.reporting_cutoffs import ledger_effective_at
from app.docx_util import write_client_account_reconcile_report_docx


def encode(value):
    if isinstance(value, datetime):
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        ).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=encode
    ).encode()


def capture_data(db, kind, row):
    cutoff = datetime.combine(
        row.period_end_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    fee = aliased(User)
    ledger = (
        select(
            LedgerEntry.id.label("entry_id"),
            LedgerEntry.pair_id,
            LedgerEntry.account_id,
            LedgerAccount.case_id,
            LedgerAccount.account_type,
            Case.case_number,
            Case.title,
            Case.client_name,
            Case.fee_earner_user_id,
            fee.display_name.label("fee_earner_name"),
            LedgerEntry.direction,
            LedgerEntry.amount_pence,
            LedgerEntry.posted_at,
            LedgerEntry.recognised_at,
            LedgerEntry.description,
            LedgerEntry.reference,
            LedgerEntry.firm_bank_account_id,
        )
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .join(Case, Case.id == LedgerAccount.case_id)
        .outerjoin(fee, fee.id == Case.fee_earner_user_id)
        .where(
            LedgerEntry.is_approved.is_(True),
            LedgerEntry.is_anticipated.is_(False),
            ledger_effective_at() < cutoff,
        )
        .order_by(LedgerEntry.id)
    )
    if kind == "bank":
        ledger = ledger.where(
            LedgerAccount.account_type == "client",
            LedgerEntry.firm_bank_account_id == row.firm_bank_account_id,
        )
    model = ClientAccountReconciliation if kind == "firm" else BankReconciliation
    queries = {
        "reconciliation": select(*model.__table__.columns).where(model.id == row.id),
        "ledger": ledger,
        "people": select(User.id, User.display_name, User.email)
        .where(User.id.in_([row.prepared_by_user_id, row.approved_by_user_id]))
        .order_by(User.id),
    }
    if kind == "bank":
        queries["bank"] = select(
            FirmBankAccount.id,
            FirmBankAccount.name,
            FirmBankAccount.account_kind,
            FirmBankAccount.sort_code,
            FirmBankAccount.account_number_last4,
        ).where(FirmBankAccount.id == row.firm_bank_account_id)
        queries["statements"] = (
            select(
                *(
                    getattr(BankStatementLine, c)
                    for c in (
                        "id",
                        "statement_date",
                        "amount_pence",
                        "description",
                        "reference",
                        "balance_pence",
                        "matched_pair_id",
                        "ignored",
                    )
                )
            )
            .where(
                BankStatementLine.firm_bank_account_id == row.firm_bank_account_id,
                BankStatementLine.statement_date <= row.period_end_date,
            )
            .order_by(BankStatementLine.id)
        )
    if kind == "firm":
        queries["firm"] = select(
            FirmSettings.trading_name,
            FirmSettings.registered_company_name,
            FirmSettings.client_bank_account_name,
            FirmSettings.client_bank_sort_code,
            FirmSettings.client_bank_account_number_last4,
            FirmSettings.client_bank_account_number,
        ).where(FirmSettings.id == 1)
    if db.get_bind().dialect.name == "postgresql":
        columns = []
        for name, query in queries.items():
            sub = query.subquery(name + "_rows")
            columns.append(
                select(
                    func.coalesce(
                        func.json_agg(func.row_to_json(sub.table_valued())),
                        literal_column("'[]'::json"),
                    )
                )
                .select_from(sub)
                .scalar_subquery()
                .label(name)
            )
        data = dict(db.execute(select(*columns)).mappings().one())
    else:
        data = {
            name: [dict(r) for r in db.execute(query).mappings()]
            for name, query in queries.items()
        }
    return json.loads(canonical(data))


def firm_report_arguments(data):
    row = data["reconciliation"][0]
    firm = (data["firm"] or [{}])[0]
    people = {p["id"]: (p["display_name"] or p["email"]) for p in data["people"]}
    return dict(
        firm_trading_name=firm.get("trading_name") or "",
        firm_registered_name=firm.get("registered_company_name"),
        **{
            k: firm.get(k)
            for k in (
                "client_bank_account_name",
                "client_bank_sort_code",
                "client_bank_account_number_last4",
                "client_bank_account_number",
            )
        },
        **{
            k: row.get(k)
            for k in (
                "period_end_date",
                "ledger_client_total_pence",
                "ledger_office_total_pence",
                "bank_statement_balance_pence",
                "difference_pence",
                "prepared_at",
                "approved_at",
                "notes",
                "status",
            )
        },
        prepared_by_name=people.get(row["prepared_by_user_id"]),
        approved_by_name=people.get(row["approved_by_user_id"]),
    )


def render_firm_docx(arguments):
    args = dict(arguments)
    if isinstance(args["period_end_date"], str):
        args["period_end_date"] = date.fromisoformat(args["period_end_date"])
    for key in ("prepared_at", "approved_at"):
        if isinstance(args.get(key), str):
            args[key] = datetime.fromisoformat(args[key])
    with tempfile.TemporaryDirectory(prefix="canary-approved-report-") as tmp:
        path = Path(tmp) / "report.docx"
        write_client_account_reconcile_report_docx(path, **args)
        return path.read_bytes()


def render_bank_html(data):
    from html import escape

    row = data["reconciliation"][0]
    bank = (data["bank"] or [{}])[0]
    details = "".join(
        f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>"
        for k, v in row.items()
    )
    return (
        '<!doctype html><meta charset="utf-8"><title>Approved bank reconciliation</title>'
        "<h1>Approved bank reconciliation</h1><p>"
        + escape(bank.get("name", ""))
        + "</p><table>"
        + details
        + "</table>"
    ).encode()

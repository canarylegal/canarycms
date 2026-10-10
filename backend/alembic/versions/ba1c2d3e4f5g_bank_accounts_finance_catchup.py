"""Firm bank accounts, payment methods, line recon, EOM, invoice alloc, Xero.

Revision ID: ba1c2d3e4f5g
Revises: hm1a2b3c4d5e
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ba1c2d3e4f5g"
down_revision = "hm1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "firm_bank_account",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("account_kind", sa.String(length=16), nullable=False, server_default="client"),
        sa.Column("sort_code", sa.String(length=16), nullable=True),
        sa.Column("account_number", sa.String(length=32), nullable=True),
        sa.Column("account_number_last4", sa.String(length=4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_firm_bank_account_kind_active", "firm_bank_account", ["account_kind", "is_active"])

    op.add_column(
        "ledger_entry",
        sa.Column("firm_bank_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("ledger_entry", sa.Column("payment_method", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_ledger_entry_firm_bank_account",
        "ledger_entry",
        "firm_bank_account",
        ["firm_bank_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_ledger_entry_firm_bank_account_id", "ledger_entry", ["firm_bank_account_id"])
    op.create_index("ix_ledger_entry_payment_method", "ledger_entry", ["payment_method"])

    op.create_table(
        "bank_statement_import",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("firm_bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=True),
        sa.Column("imported_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["firm_bank_account_id"], ["firm_bank_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "bank_statement_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("firm_bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=False),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("reference", sa.String(length=200), nullable=True),
        sa.Column("balance_pence", sa.Integer(), nullable=True),
        sa.Column("matched_pair_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matched_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ignored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["import_id"], ["bank_statement_import.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["firm_bank_account_id"], ["firm_bank_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_bank_statement_line_account_date", "bank_statement_line", ["firm_bank_account_id", "statement_date"])
    op.create_index("ix_bank_statement_line_matched_pair", "bank_statement_line", ["matched_pair_id"])

    op.create_table(
        "bank_reconciliation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("firm_bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("statement_balance_pence", sa.Integer(), nullable=False),
        sa.Column("ledger_total_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unpresented_total_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_statement_total_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("difference_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("prepared_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["firm_bank_account_id"], ["firm_bank_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("firm_bank_account_id", "period_end_date", name="uq_bank_reconciliation_account_period"),
    )

    op.create_table(
        "client_account_eom",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("firm_bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False, server_default="application/zip"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["firm_bank_account_id"], ["firm_bank_account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("firm_bank_account_id", "period_end_date", name="uq_client_account_eom_account_period"),
    )

    op.create_table(
        "case_invoice_allocation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_pair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column("allocated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["case_invoice.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["allocated_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_case_invoice_allocation_invoice", "case_invoice_allocation", ["invoice_id"])
    op.create_index("ix_case_invoice_allocation_pair", "case_invoice_allocation", ["ledger_pair_id"])

    op.add_column(
        "case_invoice",
        sa.Column("amount_allocated_pence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("case_invoice", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "inter_matter_journal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("from_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("firm_bank_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("from_pair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_pair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["from_case_id"], ["case.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_case_id"], ["case.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["firm_bank_account_id"], ["firm_bank_account.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_inter_matter_journal_created", "inter_matter_journal", ["created_at"])

    op.create_table(
        "xero_integration_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tenant_name", sa.String(length=200), nullable=True),
        sa.Column("office_income_code", sa.String(length=64), nullable=True),
        sa.Column("office_bank_code", sa.String(length=64), nullable=True),
        sa.Column("vat_code", sa.String(length=64), nullable=True),
        sa.Column("disbursement_code", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        "INSERT INTO xero_integration_settings (id, enabled) VALUES (1, false) ON CONFLICT (id) DO NOTHING"
    )

    op.create_table(
        "xero_journal_export",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False, server_default="text/csv"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )

    # Seed default client bank from legacy FirmSettings if present.
    op.execute(
        """
        INSERT INTO firm_bank_account (
          id, name, account_kind, sort_code, account_number, account_number_last4,
          is_active, is_default, created_at, updated_at
        )
        SELECT
          gen_random_uuid(),
          COALESCE(NULLIF(TRIM(client_bank_account_name), ''), 'Client account'),
          'client',
          client_bank_sort_code,
          client_bank_account_number,
          client_bank_account_number_last4,
          true,
          true,
          now(),
          now()
        FROM firm_settings
        WHERE id = 1
          AND (
            COALESCE(TRIM(client_bank_account_name), '') <> ''
            OR COALESCE(TRIM(client_bank_account_number), '') <> ''
            OR COALESCE(TRIM(client_bank_sort_code), '') <> ''
          )
          AND NOT EXISTS (SELECT 1 FROM firm_bank_account LIMIT 1)
        """
    )


def downgrade() -> None:
    op.drop_table("xero_journal_export")
    op.drop_table("xero_integration_settings")
    op.drop_index("ix_inter_matter_journal_created", table_name="inter_matter_journal")
    op.drop_table("inter_matter_journal")
    op.drop_column("case_invoice", "paid_at")
    op.drop_column("case_invoice", "amount_allocated_pence")
    op.drop_index("ix_case_invoice_allocation_pair", table_name="case_invoice_allocation")
    op.drop_index("ix_case_invoice_allocation_invoice", table_name="case_invoice_allocation")
    op.drop_table("case_invoice_allocation")
    op.drop_table("client_account_eom")
    op.drop_table("bank_reconciliation")
    op.drop_index("ix_bank_statement_line_matched_pair", table_name="bank_statement_line")
    op.drop_index("ix_bank_statement_line_account_date", table_name="bank_statement_line")
    op.drop_table("bank_statement_line")
    op.drop_table("bank_statement_import")
    op.drop_index("ix_ledger_entry_payment_method", table_name="ledger_entry")
    op.drop_index("ix_ledger_entry_firm_bank_account_id", table_name="ledger_entry")
    op.drop_constraint("fk_ledger_entry_firm_bank_account", "ledger_entry", type_="foreignkey")
    op.drop_column("ledger_entry", "payment_method")
    op.drop_column("ledger_entry", "firm_bank_account_id")
    op.drop_index("ix_firm_bank_account_kind_active", table_name="firm_bank_account")
    op.drop_table("firm_bank_account")

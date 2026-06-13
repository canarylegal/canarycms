"""Client account reconciliation snapshots and firm client bank display fields."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    reconciliation_status = postgresql.ENUM("draft", "approved", name="reconciliation_status")
    reconciliation_status.create(op.get_bind(), checkfirst=True)
    status_col = postgresql.ENUM(
        "draft",
        "approved",
        name="reconciliation_status",
        create_type=False,
    )
    op.create_table(
        "client_account_reconciliation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("ledger_client_total_pence", sa.Integer(), nullable=False),
        sa.Column("ledger_office_total_pence", sa.Integer(), nullable=False),
        sa.Column("bank_statement_balance_pence", sa.Integer(), nullable=False),
        sa.Column("difference_pence", sa.Integer(), nullable=False),
        sa.Column("prepared_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", status_col, nullable=False, server_default="draft"),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("period_end_date", name="uq_client_account_reconciliation_period_end"),
    )
    op.create_index(
        "ix_client_account_reconciliation_period_end_date",
        "client_account_reconciliation",
        ["period_end_date"],
    )
    op.add_column("firm_settings", sa.Column("client_bank_account_name", sa.String(length=200), nullable=True))
    op.add_column("firm_settings", sa.Column("client_bank_sort_code", sa.String(length=16), nullable=True))
    op.add_column(
        "firm_settings",
        sa.Column("client_bank_account_number_last4", sa.String(length=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("firm_settings", "client_bank_account_number_last4")
    op.drop_column("firm_settings", "client_bank_sort_code")
    op.drop_column("firm_settings", "client_bank_account_name")
    op.drop_index("ix_client_account_reconciliation_period_end_date", table_name="client_account_reconciliation")
    op.drop_table("client_account_reconciliation")
    reconciliation_status = postgresql.ENUM("draft", "approved", name="reconciliation_status")
    reconciliation_status.drop(op.get_bind(), checkfirst=True)

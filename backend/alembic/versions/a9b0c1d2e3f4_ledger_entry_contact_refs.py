"""Optional matter/global contact FKs on ledger_entry."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a9b0c1d2e3f4"
down_revision = "z8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ledger_entry",
        sa.Column("case_contact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "ledger_entry",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_ledger_entry_case_contact_id",
        "ledger_entry",
        "case_contact",
        ["case_contact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_ledger_entry_contact_id",
        "ledger_entry",
        "contact",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_ledger_entry_case_contact_id", "ledger_entry", ["case_contact_id"])
    op.create_index("ix_ledger_entry_contact_id", "ledger_entry", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_ledger_entry_contact_id", table_name="ledger_entry")
    op.drop_index("ix_ledger_entry_case_contact_id", table_name="ledger_entry")
    op.drop_constraint("fk_ledger_entry_contact_id", "ledger_entry", type_="foreignkey")
    op.drop_constraint("fk_ledger_entry_case_contact_id", "ledger_entry", type_="foreignkey")
    op.drop_column("ledger_entry", "contact_id")
    op.drop_column("ledger_entry", "case_contact_id")

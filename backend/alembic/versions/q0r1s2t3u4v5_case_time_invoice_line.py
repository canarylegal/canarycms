"""Link billed case_time_entry rows to case_invoice_line."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "q0r1s2t3u4v5"
down_revision = "p9q0r1s2t3u4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DO $$ BEGIN
                ALTER TABLE case_time_entry
                    ADD COLUMN invoice_line_id UUID
                    REFERENCES case_invoice_line(id) ON DELETE SET NULL;
            EXCEPTION
                WHEN duplicate_column THEN NULL;
            END $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_case_time_entry_invoice_line_id
                ON case_time_entry (invoice_line_id);
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_case_time_entry_invoice_line_id", table_name="case_time_entry")
    op.drop_column("case_time_entry", "invoice_line_id")

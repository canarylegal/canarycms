"""case_invoice.document_file_id — saved invoice .docx on matter"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h0a1b2c3d4e5"
down_revision = "g9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_invoice",
        sa.Column("document_file_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_case_invoice_document_file",
        "case_invoice",
        "file",
        ["document_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_case_invoice_document_file", "case_invoice", type_="foreignkey")
    op.drop_column("case_invoice", "document_file_id")

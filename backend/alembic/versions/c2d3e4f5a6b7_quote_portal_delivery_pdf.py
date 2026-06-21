"""Add portal PDF snapshot file on quote portal delivery."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quote_portal_delivery",
        sa.Column("portal_pdf_file_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quote_portal_delivery_portal_pdf_file_id",
        "quote_portal_delivery",
        "file",
        ["portal_pdf_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_quote_portal_delivery_portal_pdf_file",
        "quote_portal_delivery",
        ["portal_pdf_file_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_quote_portal_delivery_portal_pdf_file", table_name="quote_portal_delivery")
    op.drop_constraint("fk_quote_portal_delivery_portal_pdf_file_id", "quote_portal_delivery", type_="foreignkey")
    op.drop_column("quote_portal_delivery", "portal_pdf_file_id")

"""firm_settings.invoice_template_file_id — approved invoice .docx layout"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i1j2k3l4m5n6"
down_revision = "h0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "firm_settings",
        sa.Column("invoice_template_file_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_firm_settings_invoice_template_file",
        "firm_settings",
        "file",
        ["invoice_template_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_firm_settings_invoice_template_file", "firm_settings", type_="foreignkey")
    op.drop_column("firm_settings", "invoice_template_file_id")

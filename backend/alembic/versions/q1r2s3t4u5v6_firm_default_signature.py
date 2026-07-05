"""Firm default signature image for [FEE_EARNER_SIGNATURE] merge fallback."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "q1r2s3t4u5v6"
down_revision = "p7q8r9s0t1u2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'firm_default_signature'"))
    op.add_column(
        "firm_settings",
        sa.Column("default_signature_file_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "firm_settings",
        sa.Column(
            "default_signature_scale",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("7"),
        ),
    )
    op.create_foreign_key(
        "fk_firm_settings_default_signature_file_id",
        "firm_settings",
        "file",
        ["default_signature_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("firm_settings", "default_signature_scale", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_firm_settings_default_signature_file_id", "firm_settings", type_="foreignkey")
    op.drop_column("firm_settings", "default_signature_scale")
    op.drop_column("firm_settings", "default_signature_file_id")

"""Fee scale VAT treatment dropdown + finance item VAT column."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t9u0v1w2x3y4"
down_revision = "s7t8u9v0w1x2"
branch_labels = None
depends_on = None

_vat_treatment = sa.Enum("included", "plus_vat", name="fee_scale_vat_treatment")


def upgrade() -> None:
    _vat_treatment.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "fee_scale_line",
        sa.Column("vat_treatment", _vat_treatment, nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE fee_scale_line SET vat_treatment = 'plus_vat' WHERE include_in_vat IS TRUE"
        )
    )
    op.execute(
        sa.text(
            "UPDATE fee_scale_line SET vat_treatment = 'included' WHERE vat_treatment IS NULL"
        )
    )
    op.alter_column("fee_scale_line", "vat_treatment", nullable=False)
    op.drop_column("fee_scale_line", "include_in_vat")

    op.add_column("finance_item", sa.Column("vat_pence", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("finance_item", "vat_pence")
    op.add_column(
        "fee_scale_line",
        sa.Column("include_in_vat", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute(
        sa.text(
            "UPDATE fee_scale_line SET include_in_vat = TRUE WHERE vat_treatment = 'plus_vat'"
        )
    )
    op.drop_column("fee_scale_line", "vat_treatment")
    _vat_treatment.drop(op.get_bind(), checkfirst=True)

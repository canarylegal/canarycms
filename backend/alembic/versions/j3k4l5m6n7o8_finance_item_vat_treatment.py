"""finance_item.vat_treatment — mark manual lines as plus VAT."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j3k4l5m6n7o8"
down_revision = "i1j2k3l4m5n6"
branch_labels = None
depends_on = None

_vat_treatment = sa.Enum("included", "plus_vat", name="fee_scale_vat_treatment")


def upgrade() -> None:
    op.add_column(
        "finance_item",
        sa.Column("vat_treatment", _vat_treatment, nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE finance_item SET vat_treatment = 'plus_vat' WHERE vat_pence IS NOT NULL AND vat_pence > 0"
        )
    )


def downgrade() -> None:
    op.drop_column("finance_item", "vat_treatment")

"""Drop unused portal powered-by firm_settings columns.

Revision ID: pb1a2b3c4d5e
Revises: g2h3i4j5k6m7
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "pb1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "g2h3i4j5k6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("firm_settings", "brand_powered_by_hide")
    op.drop_column("firm_settings", "brand_powered_by_url")
    op.drop_column("firm_settings", "brand_powered_by_label")


def downgrade() -> None:
    op.add_column("firm_settings", sa.Column("brand_powered_by_label", sa.String(length=200), nullable=True))
    op.add_column("firm_settings", sa.Column("brand_powered_by_url", sa.String(length=500), nullable=True))
    op.add_column(
        "firm_settings",
        sa.Column("brand_powered_by_hide", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("firm_settings", "brand_powered_by_hide", server_default=None)

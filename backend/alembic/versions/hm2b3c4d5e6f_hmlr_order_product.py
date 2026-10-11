"""HMLR orders: product kind + wider subject field.

Revision ID: hm2b3c4d5e6f
Revises: ba1c2d3e4f5g
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "hm2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "ba1c2d3e4f5g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "hmlr_order" not in set(inspector.get_table_names()):
        return
    cols = {c["name"] for c in inspector.get_columns("hmlr_order")}
    if "product" not in cols:
        op.add_column(
            "hmlr_order",
            sa.Column(
                "product",
                sa.String(length=32),
                nullable=False,
                server_default="official_copies",
            ),
        )
    # Widen title_number so non-OC products can store party / multi-title subjects.
    op.alter_column(
        "hmlr_order",
        "title_number",
        existing_type=sa.String(length=32),
        type_=sa.String(length=256),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "hmlr_order" not in set(inspector.get_table_names()):
        return
    cols = {c["name"] for c in inspector.get_columns("hmlr_order")}
    op.alter_column(
        "hmlr_order",
        "title_number",
        existing_type=sa.String(length=256),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    if "product" in cols:
        op.drop_column("hmlr_order", "product")

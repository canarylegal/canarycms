"""Persist Casera draft product/pack selection for resume.

Revision ID: sc1a2b3c4d5e
Revises: sp1a2b3c4d5e
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "sc1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "sp1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "casera_order" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("casera_order")}
    if "selected_product_ids" not in cols:
        op.add_column(
            "casera_order",
            sa.Column(
                "selected_product_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
    if "selected_pack_ids" not in cols:
        op.add_column(
            "casera_order",
            sa.Column(
                "selected_pack_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "casera_order" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("casera_order")}
    if "selected_pack_ids" in cols:
        op.drop_column("casera_order", "selected_pack_ids")
    if "selected_product_ids" in cols:
        op.drop_column("casera_order", "selected_product_ids")

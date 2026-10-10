"""Casera finance settings, multi-file IDs, result timeline stamp.

Revision ID: sc2a2b3c4d5e
Revises: sc1a2b3c4d5e
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "sc2a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "sc1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "casera_integration_settings" in tables:
        cols = {c["name"] for c in inspector.get_columns("casera_integration_settings")}
        if "post_anticipated_disbursement" not in cols:
            op.add_column(
                "casera_integration_settings",
                sa.Column(
                    "post_anticipated_disbursement",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )
        if "add_to_completion_statement" not in cols:
            op.add_column(
                "casera_integration_settings",
                sa.Column(
                    "add_to_completion_statement",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )

    if "casera_order_product" in tables:
        cols = {c["name"] for c in inspector.get_columns("casera_order_product")}
        if "file_ids" not in cols:
            op.add_column(
                "casera_order_product",
                sa.Column(
                    "file_ids",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default=sa.text("'[]'::jsonb"),
                ),
            )
        if "result_landed_at" not in cols:
            op.add_column(
                "casera_order_product",
                sa.Column("result_landed_at", sa.DateTime(timezone=True), nullable=True),
            )
        # Backfill file_ids from file_id where empty.
        op.execute(
            sa.text(
                """
                UPDATE casera_order_product
                SET file_ids = jsonb_build_array(file_id::text)
                WHERE file_id IS NOT NULL
                  AND (file_ids IS NULL OR file_ids = '[]'::jsonb)
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "casera_order_product" in tables:
        cols = {c["name"] for c in inspector.get_columns("casera_order_product")}
        if "result_landed_at" in cols:
            op.drop_column("casera_order_product", "result_landed_at")
        if "file_ids" in cols:
            op.drop_column("casera_order_product", "file_ids")
    if "casera_integration_settings" in tables:
        cols = {c["name"] for c in inspector.get_columns("casera_integration_settings")}
        if "add_to_completion_statement" in cols:
            op.drop_column("casera_integration_settings", "add_to_completion_statement")
        if "post_anticipated_disbursement" in cols:
            op.drop_column("casera_integration_settings", "post_anticipated_disbursement")

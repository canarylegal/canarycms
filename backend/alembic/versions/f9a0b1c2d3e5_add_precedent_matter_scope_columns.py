"""Add precedent matter_head_type_id + matter_sub_type_id (ORM scope fields).

Revision ID: f9a0b1c2d3e5
Revises: e8f9a0b1c2d3
Create Date: 2026-04-28

These columns exist on ``app.models.Precedent`` but were never added via Alembic,
which breaks ``GET /precedents`` on databases created from older heads only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "f9a0b1c2d3e5"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("precedent")}
    if "matter_head_type_id" not in cols:
        op.add_column("precedent", sa.Column("matter_head_type_id", UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            "fk_precedent_matter_head_type_id",
            "precedent",
            "matter_head_type",
            ["matter_head_type_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_precedent_matter_head_type_id", "precedent", ["matter_head_type_id"])
    if "matter_sub_type_id" not in cols:
        op.add_column("precedent", sa.Column("matter_sub_type_id", UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            "fk_precedent_matter_sub_type_id",
            "precedent",
            "matter_sub_type",
            ["matter_sub_type_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_precedent_matter_sub_type_id", "precedent", ["matter_sub_type_id"])


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("precedent")}
    if "matter_sub_type_id" in cols:
        op.drop_index("ix_precedent_matter_sub_type_id", table_name="precedent")
        op.drop_constraint("fk_precedent_matter_sub_type_id", "precedent", type_="foreignkey")
        op.drop_column("precedent", "matter_sub_type_id")
    if "matter_head_type_id" in cols:
        op.drop_index("ix_precedent_matter_head_type_id", table_name="precedent")
        op.drop_constraint("fk_precedent_matter_head_type_id", "precedent", type_="foreignkey")
        op.drop_column("precedent", "matter_head_type_id")

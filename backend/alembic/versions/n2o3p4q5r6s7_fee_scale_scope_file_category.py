"""Fee scale matter scope + file_category fee_scale enum value."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'fee_scale'"))
    op.add_column(
        "fee_scale",
        sa.Column("matter_head_type_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fee_scale",
        sa.Column("matter_sub_type_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fee_scale_matter_head_type_id",
        "fee_scale",
        "matter_head_type",
        ["matter_head_type_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_fee_scale_matter_sub_type_id",
        "fee_scale",
        "matter_sub_type",
        ["matter_sub_type_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_fee_scale_matter_head_type_id", "fee_scale", ["matter_head_type_id"])
    op.create_index("ix_fee_scale_matter_sub_type_id", "fee_scale", ["matter_sub_type_id"])


def downgrade() -> None:
    op.drop_index("ix_fee_scale_matter_sub_type_id", table_name="fee_scale")
    op.drop_index("ix_fee_scale_matter_head_type_id", table_name="fee_scale")
    op.drop_constraint("fk_fee_scale_matter_sub_type_id", "fee_scale", type_="foreignkey")
    op.drop_constraint("fk_fee_scale_matter_head_type_id", "fee_scale", type_="foreignkey")
    op.drop_column("fee_scale", "matter_sub_type_id")
    op.drop_column("fee_scale", "matter_head_type_id")
    # PostgreSQL cannot remove enum label from file_category safely; leave fee_scale value.

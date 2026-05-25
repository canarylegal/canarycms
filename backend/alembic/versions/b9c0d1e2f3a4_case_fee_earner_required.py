"""Require fee_earner_user_id on every case (backfill from created_by).

Revision ID: b9c0d1e2f3a4
Revises: p3q4r5s6t7u8
Create Date: 2026-05-25

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "p3q4r5s6t7u8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE \"case\" SET fee_earner_user_id = created_by WHERE fee_earner_user_id IS NULL",
        ),
    )
    op.alter_column("case", "fee_earner_user_id", existing_type=sa.UUID(), nullable=False)


def downgrade() -> None:
    op.alter_column("case", "fee_earner_user_id", existing_type=sa.UUID(), nullable=True)

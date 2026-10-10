"""Persist matter type name snapshots on case for firm reattach.

Revision ID: g2h3i4j5k6m7
Revises: f1r2m3c4t5l6
Create Date: 2026-10-09

Live FKs into ``firm.matter_*`` are cleared on detach. Stable head/sub **names**
stay on the case so reattach can restore FKs by name match.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g2h3i4j5k6m7"
down_revision: Union[str, Sequence[str], None] = "f1r2m3c4t5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("case", sa.Column("matter_head_type_name", sa.String(length=200), nullable=True))
    op.add_column("case", sa.Column("matter_sub_type_name", sa.String(length=200), nullable=True))
    # Backfill from live catalogue when FKs are present (tables live in firm schema).
    op.execute(
        sa.text(
            """
            UPDATE "case" AS c
            SET matter_sub_type_name = s.name,
                matter_head_type_name = COALESCE(h.name, c.matter_head_type_name)
            FROM firm.matter_sub_type AS s
            LEFT JOIN firm.matter_head_type AS h ON h.id = s.head_type_id
            WHERE c.matter_sub_type_id = s.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE "case" AS c
            SET matter_head_type_name = h.name
            FROM firm.matter_head_type AS h
            WHERE c.matter_head_type_id = h.id
              AND c.matter_head_type_name IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("case", "matter_sub_type_name")
    op.drop_column("case", "matter_head_type_name")

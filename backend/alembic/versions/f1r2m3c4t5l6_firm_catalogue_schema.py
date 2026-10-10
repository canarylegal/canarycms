"""Move firm catalogue tables into schema ``firm``.

Revision ID: f1r2m3c4t5l6
Revises: c9a8b7c6d5e4
Create Date: 2026-10-09

Firm-owned catalogue (matter types, fee scales, portal form definitions,
precedents) moves to Postgres schema ``firm``. Core ``public`` keeps users,
cases, file metadata, portal submissions, and favorites that FK into firm.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1r2m3c4t5l6"
down_revision: Union[str, Sequence[str], None] = "c9a8b7c6d5e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FIRM = "firm"

_TABLES: tuple[str, ...] = (
    "matter_sub_type_menu",
    "matter_sub_type_event_template",
    "matter_sub_type_standard_task",
    "fee_scale_line",
    "fee_scale_band_row",
    "fee_scale_band_set",
    "fee_scale_category",
    "fee_scale",
    "portal_form_template_field",
    "portal_form_template",
    "precedent",
    "precedent_category",
    "matter_sub_type",
    "matter_head_type",
)


def _table_in_schema(conn, table: str, schema: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema = :s AND table_name = :t
                )
                """
            ),
            {"s": schema, "t": table},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{FIRM}"'))
    for table in _TABLES:
        if _table_in_schema(conn, table, FIRM):
            continue
        if not _table_in_schema(conn, table, "public"):
            continue
        op.execute(sa.text(f'ALTER TABLE "{table}" SET SCHEMA "{FIRM}"'))


def downgrade() -> None:
    conn = op.get_bind()
    for table in reversed(_TABLES):
        if _table_in_schema(conn, table, "public"):
            continue
        if not _table_in_schema(conn, table, FIRM):
            continue
        op.execute(sa.text(f'ALTER TABLE "{FIRM}"."{table}" SET SCHEMA public'))

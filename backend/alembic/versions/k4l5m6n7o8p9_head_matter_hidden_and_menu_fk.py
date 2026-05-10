"""Head matter types: is_hidden; sub-menus FK RESTRICT on sub-type delete.

Revision ID: k4l5m6n7o8p9
Revises: h3i4j5k6l7m8
Create Date: 2026-05-04

- ``is_hidden``: firms can hide Canary head types they do not use (admins only).
- ``matter_sub_type_menu.sub_type_id``: ON DELETE CASCADE → RESTRICT so deleting
  a sub-matter type does not silently remove sub-menus; remove menus first.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "k4l5m6n7o8p9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matter_head_type",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("matter_head_type", "is_hidden", server_default=None)

    bind = op.get_bind()
    insp = inspect(bind)
    fks = insp.get_foreign_keys("matter_sub_type_menu")
    for fk in fks:
        if fk.get("referred_table") == "matter_sub_type" and "sub_type_id" in (fk.get("constrained_columns") or []):
            op.drop_constraint(fk["name"], "matter_sub_type_menu", type_="foreignkey")
            break
    op.create_foreign_key(
        "matter_sub_type_menu_sub_type_id_fkey",
        "matter_sub_type_menu",
        "matter_sub_type",
        ["sub_type_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    fks = insp.get_foreign_keys("matter_sub_type_menu")
    for fk in fks:
        if fk.get("referred_table") == "matter_sub_type" and "sub_type_id" in (fk.get("constrained_columns") or []):
            op.drop_constraint(fk["name"], "matter_sub_type_menu", type_="foreignkey")
            break
    op.create_foreign_key(
        "matter_sub_type_menu_sub_type_id_fkey",
        "matter_sub_type_menu",
        "matter_sub_type",
        ["sub_type_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("matter_head_type", "is_hidden")

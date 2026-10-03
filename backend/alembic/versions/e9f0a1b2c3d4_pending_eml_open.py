"""Pending Thunderbird open for filed .eml messages.

Revision ID: e9f0a1b2c3d4
Revises: ab2c3d4e5f6a
Create Date: 2026-10-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "e9f0a1b2c3d4"
down_revision = "ab2c3d4e5f6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("user")}
    if "outlook_pending_eml_open_case_id" not in cols:
        op.add_column(
            "user",
            sa.Column("outlook_pending_eml_open_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_user_pending_eml_open_case_id",
            "user",
            "case",
            ["outlook_pending_eml_open_case_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "outlook_pending_eml_open_file_id" not in cols:
        op.add_column(
            "user",
            sa.Column("outlook_pending_eml_open_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_user_pending_eml_open_file_id",
            "user",
            "file",
            ["outlook_pending_eml_open_file_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "outlook_pending_eml_open_expires_at" not in cols:
        op.add_column(
            "user",
            sa.Column("outlook_pending_eml_open_expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("user")}
    fks = {fk["name"] for fk in inspect(bind).get_foreign_keys("user")}
    if "fk_user_pending_eml_open_file_id" in fks:
        op.drop_constraint("fk_user_pending_eml_open_file_id", "user", type_="foreignkey")
    if "fk_user_pending_eml_open_case_id" in fks:
        op.drop_constraint("fk_user_pending_eml_open_case_id", "user", type_="foreignkey")
    if "outlook_pending_eml_open_expires_at" in cols:
        op.drop_column("user", "outlook_pending_eml_open_expires_at")
    if "outlook_pending_eml_open_file_id" in cols:
        op.drop_column("user", "outlook_pending_eml_open_file_id")
    if "outlook_pending_eml_open_case_id" in cols:
        op.drop_column("user", "outlook_pending_eml_open_case_id")

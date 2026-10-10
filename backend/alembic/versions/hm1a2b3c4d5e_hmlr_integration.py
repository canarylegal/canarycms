"""HM Land Registry Business Gateway integration (settings + orders).

Revision ID: hm1a2b3c4d5e
Revises: sc3a2b3c4d5e
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "hm1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "sc3a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "hmlr_integration_settings" not in tables:
        op.create_table(
            "hmlr_integration_settings",
            sa.Column("id", sa.SmallInteger(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("sandbox", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("username", sa.Text(), nullable=True),
            sa.Column("password_enc", sa.Text(), nullable=True),
            sa.Column("customer_reference", sa.String(128), nullable=True),
            sa.Column("contact_name", sa.String(256), nullable=True),
            sa.Column("contact_phone", sa.String(64), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.execute(sa.text("INSERT INTO hmlr_integration_settings (id) VALUES (1) ON CONFLICT DO NOTHING"))

    if "hmlr_order" not in tables:
        op.create_table(
            "hmlr_order",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title_number", sa.String(32), nullable=False),
            sa.Column("external_reference", sa.String(128), nullable=False, server_default=""),
            sa.Column("want_register", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("want_title_plan", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("state", sa.String(64), nullable=False, server_default="Draft"),
            sa.Column("gateway_message_id", sa.String(128), nullable=True),
            sa.Column("poll_after", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fee_pence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("register_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
            sa.Column("plan_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
            sa.Column("sandbox", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_hmlr_order_case_id", "hmlr_order", ["case_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "hmlr_order" in tables:
        op.drop_index("ix_hmlr_order_case_id", table_name="hmlr_order")
        op.drop_table("hmlr_order")
    if "hmlr_integration_settings" in tables:
        op.drop_table("hmlr_integration_settings")

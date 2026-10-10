"""Casera searches integration settings, orders, and webhook idempotency."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c9a8b7c6d5e4"
down_revision = "p8a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "casera_integration_settings" not in existing:
        op.create_table(
            "casera_integration_settings",
            sa.Column("id", sa.SmallInteger(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("sandbox", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("client_id", sa.Text(), nullable=True),
            sa.Column("access_token_enc", sa.Text(), nullable=True),
            sa.Column("webhook_secret_enc", sa.Text(), nullable=True),
            sa.Column("webhook_path_token", sa.Text(), nullable=True),
            sa.Column("api_base_uri", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.execute(sa.text("INSERT INTO casera_integration_settings (id) VALUES (1) ON CONFLICT DO NOTHING"))

    if "casera_case_link" not in existing:
        op.create_table(
            "casera_case_link",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
            sa.Column("casera_case_id", sa.String(128), nullable=False),
            sa.Column("casera_reference", sa.String(256), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("case_id", name="uq_casera_case_link_case_id"),
            sa.UniqueConstraint("casera_case_id", name="uq_casera_case_link_casera_case_id"),
        )
        op.create_index("ix_casera_case_link_case_id", "casera_case_link", ["case_id"])

    if "casera_order" not in existing:
        op.create_table(
            "casera_order",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
            sa.Column("casera_order_id", sa.String(128), nullable=False),
            sa.Column("casera_case_id", sa.String(128), nullable=False),
            sa.Column("category", sa.String(64), nullable=False, server_default="Conveyancing"),
            sa.Column("state", sa.String(64), nullable=False, server_default="Draft"),
            sa.Column("total_pence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("casera_order_id", name="uq_casera_order_casera_order_id"),
        )
        op.create_index("ix_casera_order_case_id", "casera_order", ["case_id"])

    if "casera_order_product" not in existing:
        op.create_table(
            "casera_order_product",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "order_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("casera_order.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("casera_product_id", sa.String(128), nullable=False),
            sa.Column("casera_order_product_id", sa.String(128), nullable=True),
            sa.Column("name", sa.String(512), nullable=False, server_default=""),
            sa.Column("state", sa.String(64), nullable=False, server_default="Idle"),
            sa.Column("price_pence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "file_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("file.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_casera_order_product_order_id", "casera_order_product", ["order_id"])
        op.create_index("ix_casera_order_product_file_id", "casera_order_product", ["file_id"])
        op.create_index(
            "ix_casera_order_product_casera_op_id",
            "casera_order_product",
            ["casera_order_product_id"],
        )

    if "casera_webhook_event" not in existing:
        op.create_table(
            "casera_webhook_event",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("event_key", sa.String(256), nullable=False),
            sa.Column("event_type", sa.String(128), nullable=False),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("event_key", name="uq_casera_webhook_event_key"),
        )


def downgrade() -> None:
    op.drop_table("casera_webhook_event")
    op.drop_table("casera_order_product")
    op.drop_table("casera_order")
    op.drop_table("casera_case_link")
    op.drop_table("casera_integration_settings")

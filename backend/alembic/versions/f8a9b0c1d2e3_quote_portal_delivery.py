"""Quote portal delivery (client accept/decline via portal)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8a9b0c1d2e3"
down_revision = "h0i1j2k3l4m5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "pending",
        "accepted",
        "declined",
        "superseded",
        name="quote_portal_delivery_status",
    )
    status.create(op.get_bind(), checkfirst=True)
    status_col = postgresql.ENUM(
        "pending",
        "accepted",
        "declined",
        "superseded",
        name="quote_portal_delivery_status",
        create_type=False,
    )
    op.create_table(
        "quote_portal_delivery",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "grant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact_portal_grant.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sent_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("file_version_at_send", sa.Integer(), nullable=False),
        sa.Column("status", status_col, nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_quote_portal_delivery_case", "quote_portal_delivery", ["case_id"])
    op.create_index("ix_quote_portal_delivery_file", "quote_portal_delivery", ["file_id"])
    op.create_index("ix_quote_portal_delivery_contact", "quote_portal_delivery", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_quote_portal_delivery_contact", table_name="quote_portal_delivery")
    op.drop_index("ix_quote_portal_delivery_file", table_name="quote_portal_delivery")
    op.drop_index("ix_quote_portal_delivery_case", table_name="quote_portal_delivery")
    op.drop_table("quote_portal_delivery")
    postgresql.ENUM(name="quote_portal_delivery_status").drop(op.get_bind(), checkfirst=True)

"""Client portal access codes and folder grants.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_portal_access",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("contact_id", name="uq_contact_portal_access_contact_id"),
        sa.UniqueConstraint("code_sha256", name="uq_contact_portal_access_code_sha256"),
    )
    op.create_index("ix_contact_portal_access_code_sha256", "contact_portal_access", ["code_sha256"])

    op.create_table(
        "contact_portal_grant",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("folder_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("label", sa.String(length=300), nullable=True),
        sa.Column("can_download", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("can_upload", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_contact_portal_grant_contact_id", "contact_portal_grant", ["contact_id"])
    op.create_index("ix_contact_portal_grant_case_id", "contact_portal_grant", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_contact_portal_grant_case_id", table_name="contact_portal_grant")
    op.drop_index("ix_contact_portal_grant_contact_id", table_name="contact_portal_grant")
    op.drop_table("contact_portal_grant")
    op.drop_index("ix_contact_portal_access_code_sha256", table_name="contact_portal_access")
    op.drop_table("contact_portal_access")

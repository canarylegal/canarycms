"""Matter-scoped portal access for non-client exchange contacts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "u5v6w7x8y9z0"
down_revision = "t4u5v6w7x8y9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matter_portal_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_sha256", sa.String(64), nullable=False),
        sa.Column("code_enc", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_folder_shared", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("case_id", "contact_id", name="uq_matter_portal_access_case_contact"),
        sa.UniqueConstraint("code_sha256", name="uq_matter_portal_access_code_sha256"),
    )
    op.create_index("ix_matter_portal_access_case_id", "matter_portal_access", ["case_id"])
    op.create_index("ix_matter_portal_access_contact_id", "matter_portal_access", ["contact_id"])
    op.create_index("ix_matter_portal_access_code_sha256", "matter_portal_access", ["code_sha256"])


def downgrade() -> None:
    op.drop_index("ix_matter_portal_access_code_sha256", table_name="matter_portal_access")
    op.drop_index("ix_matter_portal_access_contact_id", table_name="matter_portal_access")
    op.drop_index("ix_matter_portal_access_case_id", table_name="matter_portal_access")
    op.drop_table("matter_portal_access")

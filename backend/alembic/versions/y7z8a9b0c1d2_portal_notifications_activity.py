"""Portal notification prefs, staff recipients, activity log, e-mail OTP login."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "y7z8a9b0c1d2"
down_revision = "x6y7z8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contact_portal_access",
        sa.Column("notify_files_added", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "contact_portal_access",
        sa.Column("notify_folder_shared", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "case_portal_staff_recipient",
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "portal_activity_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contact.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grant_id", UUID(as_uuid=True), sa.ForeignKey("contact_portal_grant.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_portal_activity_event_case_created", "portal_activity_event", ["case_id", "created_at"])

    op.create_table(
        "portal_login_otp",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_portal_login_otp_contact_created", "portal_login_otp", ["contact_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_portal_login_otp_contact_created", table_name="portal_login_otp")
    op.drop_table("portal_login_otp")
    op.drop_index("ix_portal_activity_event_case_created", table_name="portal_activity_event")
    op.drop_table("portal_activity_event")
    op.drop_table("case_portal_staff_recipient")
    op.drop_column("contact_portal_access", "notify_folder_shared")
    op.drop_column("contact_portal_access", "notify_files_added")

"""Add fillable PDF (AcroForm) lock + responses to Canary Sign requests."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "s3t4u5v6w7x8"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE canary_sign_audit_event_type ADD VALUE IF NOT EXISTS 'form_locked'"))
    op.execute(sa.text("ALTER TYPE canary_sign_audit_event_type ADD VALUE IF NOT EXISTS 'form_filled'"))

    op.add_column(
        "canary_sign_request",
        sa.Column("has_fillable_form", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "canary_sign_request",
        sa.Column("form_locked_by_recipient_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "canary_sign_request",
        sa.Column("form_locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "canary_sign_request",
        sa.Column("form_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "canary_sign_request",
        sa.Column("form_responses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_canary_sign_request_form_locked_by",
        "canary_sign_request",
        "canary_sign_recipient",
        ["form_locked_by_recipient_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_canary_sign_request_form_locked_by", "canary_sign_request", type_="foreignkey")
    op.drop_column("canary_sign_request", "form_responses")
    op.drop_column("canary_sign_request", "form_completed_at")
    op.drop_column("canary_sign_request", "form_locked_at")
    op.drop_column("canary_sign_request", "form_locked_by_recipient_id")
    op.drop_column("canary_sign_request", "has_fillable_form")

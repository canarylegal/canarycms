"""Durable Canary Sign recipient delivery bindings; no historical messages queued."""

from alembic import op
import sqlalchemy as sa

revision = "fea6f7a8b9c0"
down_revision = "fea5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "notification_outbox",
        "recipient_user_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.add_column(
        "notification_outbox", sa.Column("signing_request_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "notification_outbox",
        sa.Column("signing_recipient_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "notification_outbox", sa.Column("binding_enc", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_notification_outbox_signing_request_id",
        "notification_outbox",
        ["signing_request_id"],
    )
    op.create_check_constraint(
        "ck_notification_recipient_scope",
        "notification_outbox",
        "(recipient_user_id IS NOT NULL AND signing_request_id IS NULL AND signing_recipient_id IS NULL AND binding_enc IS NULL) OR (recipient_user_id IS NULL AND signing_request_id IS NOT NULL AND signing_recipient_id IS NOT NULL AND binding_enc IS NOT NULL AND kind IN ('canary_sign_requested','canary_sign_reminded'))",
    )


def downgrade():
    raise RuntimeError("Retain recipient delivery evidence; roll forward instead")

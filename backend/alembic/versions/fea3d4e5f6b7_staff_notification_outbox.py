"""Transactional staff notification outbox. No scheduling or historical backfill."""

from alembic import op
import sqlalchemy as sa

revision = "fea3d4e5f6b7"
down_revision = "fea2d3e4f5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("event_key", sa.String(240), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("payload_enc", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_code", sa.String(80), nullable=True),
        sa.CheckConstraint(
            "state IN ('pending','sending','sent','failed','uncertain','cancelled')",
            name="ck_notification_state",
        ),
    )
    op.create_index("ix_notification_outbox_state", "notification_outbox", ["state"])
    op.create_table(
        "notification_attempt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "notification_id",
            sa.Uuid(),
            sa.ForeignKey("notification_outbox.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("transport", sa.String(16), nullable=True),
        sa.Column("code", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_attempt_notification_id",
        "notification_attempt",
        ["notification_id"],
    )


def downgrade():
    raise RuntimeError("Retain notification delivery evidence; roll forward instead")

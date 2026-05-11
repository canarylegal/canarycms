"""SMTP notification settings, calendar e-mail alert subscriptions, template notify fields.

Revision ID: v3w4x5y6z7a8
Revises: b5c6d7e8f9a0
Create Date: 2026-05-11

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v3w4x5y6z7a8"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smtp_notification_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("host", sa.String(length=300), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("username", sa.String(length=320), nullable=True),
        sa.Column("password_enc", sa.Text(), nullable=True),
        sa.Column("from_email", sa.String(length=320), nullable=True),
        sa.Column("from_name", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("INSERT INTO smtp_notification_settings (id) VALUES (1)")

    op.create_table(
        "calendar_event_email_alert_subscription",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("anchor_date", sa.Date(), nullable=True),
        sa.Column("anchor_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("title_snapshot", sa.String(length=600), nullable=False, server_default=""),
        sa.Column("matter_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "event_key", name="uq_cal_ev_mail_sub_user_event"),
    )
    op.create_index("ix_cal_ev_mail_sub_user", "calendar_event_email_alert_subscription", ["user_id"])

    op.create_table(
        "calendar_event_notification_sent",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(length=512), nullable=False),
        sa.Column("sent_day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "event_key", "sent_day", "kind", name="uq_cal_ev_notif_sent_dedupe"),
    )
    op.create_index("ix_cal_ev_notif_sent_user_day", "calendar_event_notification_sent", ["user_id", "sent_day"])

    op.add_column(
        "matter_sub_type_event_template",
        sa.Column("notify_on_day", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("matter_sub_type_event_template", sa.Column("notify_every_n", sa.Integer(), nullable=True))
    op.add_column("matter_sub_type_event_template", sa.Column("notify_every_unit", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column("matter_sub_type_event_template", "notify_every_unit")
    op.drop_column("matter_sub_type_event_template", "notify_every_n")
    op.drop_column("matter_sub_type_event_template", "notify_on_day")
    op.drop_table("calendar_event_notification_sent")
    op.drop_table("calendar_event_email_alert_subscription")
    op.drop_table("smtp_notification_settings")

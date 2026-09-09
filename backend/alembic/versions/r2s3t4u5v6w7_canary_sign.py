"""Canary Sign built-in e-sign requests, recipients, fields, and audit."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "r2s3t4u5v6w7"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


def _ensure_enum(name: str, values: list[str]) -> None:
    labels = ", ".join(f"'{v}'" for v in values)
    op.execute(
        sa.text(
            f"""
            DO $$ BEGIN
                CREATE TYPE {name} AS ENUM ({labels});
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    _ensure_enum("canary_sign_status", ["pending", "completed", "declined", "voided", "expired"])
    _ensure_enum("canary_sign_recipient_status", ["pending", "viewed", "signed", "declined"])
    _ensure_enum("canary_sign_order_mode", ["parallel", "sequential"])
    _ensure_enum(
        "canary_sign_field_type",
        ["signature", "initials", "date", "printed_name", "checkbox"],
    )
    _ensure_enum(
        "canary_sign_audit_event_type",
        ["created", "sent", "viewed", "signed", "declined", "voided", "reminded", "completed", "expired"],
    )

    sign_status = postgresql.ENUM(name="canary_sign_status", create_type=False)
    recip_status = postgresql.ENUM(name="canary_sign_recipient_status", create_type=False)
    order_mode = postgresql.ENUM(name="canary_sign_order_mode", create_type=False)
    field_type = postgresql.ENUM(name="canary_sign_field_type", create_type=False)
    audit_type = postgresql.ENUM(name="canary_sign_audit_event_type", create_type=False)

    if "canary_sign_request" not in existing:
        op.create_table(
            "canary_sign_request",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "source_file_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("file.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "snapshot_pdf_file_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("file.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "signed_file_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("file.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "certificate_file_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("file.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "sent_by_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("user.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "supersedes_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("canary_sign_request.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("subject", sa.String(500), nullable=False, server_default=""),
            sa.Column("status", sign_status, nullable=False, server_default="pending"),
            sa.Column("status_detail", sa.Text(), nullable=True),
            sa.Column("order_mode", order_mode, nullable=False, server_default="parallel"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_canary_sign_request_case_id", "canary_sign_request", ["case_id"])
        op.create_index("ix_canary_sign_request_source_file_id", "canary_sign_request", ["source_file_id"])
        op.create_index("ix_canary_sign_request_status", "canary_sign_request", ["status"])

    if "canary_sign_recipient" not in existing:
        op.create_table(
            "canary_sign_recipient",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "signing_request_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("canary_sign_request.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "case_contact_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("case_contact.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "contact_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("contact.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("name", sa.String(300), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("routing_order", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("sign_token", sa.String(64), nullable=False),
            sa.Column("status", recip_status, nullable=False, server_default="pending"),
            sa.Column("decline_reason", sa.Text(), nullable=True),
            sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("signed_ip", sa.String(64), nullable=True),
            sa.Column("signed_user_agent", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("sign_token", name="uq_canary_sign_recipient_sign_token"),
        )
        op.create_index("ix_canary_sign_recipient_request_id", "canary_sign_recipient", ["signing_request_id"])
        op.create_index("ix_canary_sign_recipient_contact_id", "canary_sign_recipient", ["contact_id"])

    if "canary_sign_field" not in existing:
        op.create_table(
            "canary_sign_field",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "signing_request_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("canary_sign_request.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "recipient_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("canary_sign_recipient.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("field_type", field_type, nullable=False),
            sa.Column("label", sa.String(200), nullable=True),
            sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("placement_mode", sa.String(16), nullable=False, server_default="free"),
            sa.Column("page", sa.Integer(), nullable=True),
            sa.Column("x_pct", sa.Float(), nullable=True),
            sa.Column("y_pct", sa.Float(), nullable=True),
            sa.Column("w_pct", sa.Float(), nullable=True),
            sa.Column("h_pct", sa.Float(), nullable=True),
            sa.Column("value", postgresql.JSONB(), nullable=True),
            sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_canary_sign_field_request_id", "canary_sign_field", ["signing_request_id"])
        op.create_index("ix_canary_sign_field_recipient_id", "canary_sign_field", ["recipient_id"])

    if "canary_sign_audit_event" not in existing:
        op.create_table(
            "canary_sign_audit_event",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "signing_request_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("canary_sign_request.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "recipient_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("canary_sign_recipient.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("event_type", audit_type, nullable=False),
            sa.Column("detail", postgresql.JSONB(), nullable=True),
            sa.Column("ip", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_canary_sign_audit_event_request_id", "canary_sign_audit_event", ["signing_request_id"])
        op.create_index("ix_canary_sign_audit_event_created_at", "canary_sign_audit_event", ["created_at"])


def downgrade() -> None:
    op.drop_table("canary_sign_audit_event")
    op.drop_table("canary_sign_field")
    op.drop_table("canary_sign_recipient")
    op.drop_table("canary_sign_request")
    op.execute(sa.text("DROP TYPE IF EXISTS canary_sign_audit_event_type"))
    op.execute(sa.text("DROP TYPE IF EXISTS canary_sign_field_type"))
    op.execute(sa.text("DROP TYPE IF EXISTS canary_sign_order_mode"))
    op.execute(sa.text("DROP TYPE IF EXISTS canary_sign_recipient_status"))
    op.execute(sa.text("DROP TYPE IF EXISTS canary_sign_status"))

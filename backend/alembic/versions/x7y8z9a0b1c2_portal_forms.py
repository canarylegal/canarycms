"""Portal form templates (precedents) and matter submissions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "x7y8z9a0b1c2"
down_revision = "w6x7y8z9a0b1"
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
    _ensure_enum("portal_form_field_type", ["section", "text", "textarea", "date", "yes_no", "file"])
    _ensure_enum("portal_form_submission_status", ["pending", "completed", "voided", "superseded"])

    field_type = postgresql.ENUM(
        "section",
        "text",
        "textarea",
        "date",
        "yes_no",
        "file",
        name="portal_form_field_type",
        create_type=False,
    )
    submission_status = postgresql.ENUM(
        "pending",
        "completed",
        "voided",
        "superseded",
        name="portal_form_submission_status",
        create_type=False,
    )

    op.create_table(
        "portal_form_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "matter_head_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matter_head_type.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "matter_sub_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matter_sub_type.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("reference", name="uq_portal_form_template_reference"),
    )
    op.create_index("ix_portal_form_template_head", "portal_form_template", ["matter_head_type_id"])
    op.create_index("ix_portal_form_template_sub", "portal_form_template", ["matter_sub_type_id"])

    op.create_table(
        "portal_form_template_field",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portal_form_template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("field_type", field_type, nullable=False),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("template_id", "field_key", name="uq_portal_form_template_field_key"),
    )
    op.create_index("ix_portal_form_template_field_template", "portal_form_template_field", ["template_id"])

    op.create_table(
        "portal_form_submission",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portal_form_template.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portal_form_submission.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", submission_status, nullable=False, server_default="pending"),
        sa.Column("responses", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "snapshot_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("file.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_portal_form_submission_case", "portal_form_submission", ["case_id"])
    op.create_index("ix_portal_form_submission_contact", "portal_form_submission", ["contact_id"])
    op.create_index("ix_portal_form_submission_template", "portal_form_submission", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_portal_form_submission_template", table_name="portal_form_submission")
    op.drop_index("ix_portal_form_submission_contact", table_name="portal_form_submission")
    op.drop_index("ix_portal_form_submission_case", table_name="portal_form_submission")
    op.drop_table("portal_form_submission")
    op.drop_index("ix_portal_form_template_field_template", table_name="portal_form_template_field")
    op.drop_table("portal_form_template_field")
    op.drop_index("ix_portal_form_template_sub", table_name="portal_form_template")
    op.drop_index("ix_portal_form_template_head", table_name="portal_form_template")
    op.drop_table("portal_form_template")
    op.execute(sa.text("DROP TYPE IF EXISTS portal_form_submission_status"))
    op.execute(sa.text("DROP TYPE IF EXISTS portal_form_field_type"))

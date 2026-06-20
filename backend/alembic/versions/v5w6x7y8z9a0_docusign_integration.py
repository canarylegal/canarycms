"""DocuSign integration settings and matter signing requests."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v5w6x7y8z9a0"
down_revision = "u4v5w6x7y8z9"
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

    if "docusign_integration_settings" not in existing:
        op.create_table(
            "docusign_integration_settings",
            sa.Column("id", sa.SmallInteger(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("use_demo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allow_tier_a", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allow_tier_b", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_tier_c", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_wes", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allow_qes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("account_id", sa.Text(), nullable=True),
            sa.Column("integration_key", sa.Text(), nullable=True),
            sa.Column("user_id", sa.Text(), nullable=True),
            sa.Column("rsa_private_key_enc", sa.Text(), nullable=True),
            sa.Column("connect_hmac_secret_enc", sa.Text(), nullable=True),
            sa.Column("api_base_uri", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.execute(sa.text("INSERT INTO docusign_integration_settings (id) VALUES (1) ON CONFLICT DO NOTHING"))

    _ensure_enum("docusign_signing_status", ["pending", "completed", "declined", "voided", "expired", "error"])
    _ensure_enum("docusign_document_tier", ["a", "b", "c"])
    _ensure_enum("docusign_signature_level", ["standard", "wes", "qes"])
    _ensure_enum("docusign_recipient_status", ["pending", "sent", "delivered", "completed", "declined", "autoresponded"])

    signing_status = postgresql.ENUM(name="docusign_signing_status", create_type=False)
    doc_tier = postgresql.ENUM(name="docusign_document_tier", create_type=False)
    sig_level = postgresql.ENUM(name="docusign_signature_level", create_type=False)
    recipient_status = postgresql.ENUM(name="docusign_recipient_status", create_type=False)

    if "docusign_signing_request" not in existing:
        op.create_table(
            "docusign_signing_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sent_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("docusign_signing_request.id", ondelete="SET NULL"), nullable=True),
        sa.Column("docusign_envelope_id", sa.String(64), nullable=True),
        sa.Column("docusign_template_id", sa.String(64), nullable=True),
        sa.Column("envelope_subject", sa.String(500), nullable=False, server_default=""),
        sa.Column("document_tier", doc_tier, nullable=False, server_default="a"),
        sa.Column("signature_level", sig_level, nullable=False, server_default="standard"),
        sa.Column("status", signing_status, nullable=False, server_default="pending"),
        sa.Column("signed_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
        sa.Column("certificate_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_docusign_signing_request_case_id", "docusign_signing_request", ["case_id"])
        op.create_index("ix_docusign_signing_request_source_file_id", "docusign_signing_request", ["source_file_id"])
        op.create_index("ix_docusign_signing_request_envelope_id", "docusign_signing_request", ["docusign_envelope_id"])

    if "docusign_signing_recipient" not in existing:
        op.create_table(
            "docusign_signing_recipient",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signing_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("docusign_signing_request.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_contact.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("routing_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("role_name", sa.String(100), nullable=True),
        sa.Column("docusign_recipient_id", sa.String(32), nullable=True),
        sa.Column("client_user_id", sa.String(64), nullable=False),
        sa.Column("sign_token", sa.String(64), nullable=False),
        sa.Column("status", recipient_status, nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("sign_token", name="uq_docusign_signing_recipient_sign_token"),
        )
        op.create_index("ix_docusign_signing_recipient_request_id", "docusign_signing_recipient", ["signing_request_id"])


def downgrade() -> None:
    op.drop_table("docusign_signing_recipient")
    op.drop_table("docusign_signing_request")
    op.drop_table("docusign_integration_settings")
    op.execute(sa.text("DROP TYPE IF EXISTS docusign_recipient_status"))
    op.execute(sa.text("DROP TYPE IF EXISTS docusign_signature_level"))
    op.execute(sa.text("DROP TYPE IF EXISTS docusign_document_tier"))
    op.execute(sa.text("DROP TYPE IF EXISTS docusign_signing_status"))

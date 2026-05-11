"""Passkeys (WebAuthn) + firm mandate for second factor (TOTP or passkey)

Revision ID: a4b5c6d7e8f9
Revises: z2a3b4c5d6e7
Create Date: 2026-05-10

Cross-branch: ``firm_settings`` is created in ``q9w0e1r2t3y4`` (parallel to ``z2a3b4c5d6e7``).
``depends_on`` ensures that revision runs before this one on fresh databases (Alembic >= 1.10).

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a4b5c6d7e8f9"
down_revision = "z2a3b4c5d6e7"
branch_labels = None
depends_on = ("q9w0e1r2t3y4",)


def upgrade() -> None:
    op.add_column(
        "firm_settings",
        sa.Column("mandate_two_factor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "webauthn_challenge",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=320), nullable=False),
        sa.Column("challenge_b64", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_webauthn_challenge_subject"), "webauthn_challenge", ["subject"], unique=False)

    op.create_table(
        "webauthn_credential",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("transports", sa.String(length=200), nullable=True),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id", name="uq_webauthn_credential_credential_id"),
    )
    op.create_index(op.f("ix_webauthn_credential_user_id"), "webauthn_credential", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_webauthn_credential_user_id"), table_name="webauthn_credential")
    op.drop_table("webauthn_credential")
    op.drop_index(op.f("ix_webauthn_challenge_subject"), table_name="webauthn_challenge")
    op.drop_table("webauthn_challenge")
    op.drop_column("firm_settings", "mandate_two_factor")

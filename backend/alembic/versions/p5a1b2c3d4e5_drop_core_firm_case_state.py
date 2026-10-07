"""Drop legacy core firm_module_case_state (Phase 5 — data lives in firm schema).

Revision ID: p5a1b2c3d4e5
Revises: p3a1b2c3d4e5
Create Date: 2026-10-07

Requires firm migrations to have copied rows into firm_example_pilot.case_state first
(``python -m app.firm_module_migrate``). Outbox table stays in public.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p5a1b2c3d4e5"
down_revision = "p3a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    firm_exists = conn.execute(
        sa.text("SELECT to_regclass('firm_example_pilot.case_state') IS NOT NULL")
    ).scalar()
    legacy_exists = conn.execute(
        sa.text("SELECT to_regclass('public.firm_module_case_state') IS NOT NULL")
    ).scalar()
    legacy_count = 0
    if legacy_exists:
        legacy_count = int(
            conn.execute(sa.text("SELECT COUNT(*) FROM public.firm_module_case_state")).scalar() or 0
        )
    if legacy_count and not firm_exists:
        raise RuntimeError(
            "Refusing to drop public.firm_module_case_state: firm_example_pilot.case_state "
            "missing. Run `python -m app.firm_module_migrate` before this Alembic revision."
        )
    if legacy_exists:
        op.drop_index("ix_firm_module_case_state_case_id", table_name="firm_module_case_state")
        op.drop_table("firm_module_case_state")


def downgrade() -> None:
    op.create_table(
        "firm_module_case_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("module_id", sa.String(length=80), nullable=False),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("module_id", "case_id", name="uq_firm_module_case_state_module_case"),
    )
    op.create_index("ix_firm_module_case_state_case_id", "firm_module_case_state", ["case_id"])

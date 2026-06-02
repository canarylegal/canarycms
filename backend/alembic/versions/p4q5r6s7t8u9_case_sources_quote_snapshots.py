"""Case referral sources, case.source_id, and quote line snapshots for finance."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None

_DEFAULT_SOURCES = (
    "Existing client",
    "Word of mouth",
    "Social media",
    "Marketing",
    "Search engine",
)


def upgrade() -> None:
    op.create_table(
        "case_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_case_source_name"),
    )
    op.add_column(
        "case",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_source.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_case_source_id", "case", ["source_id"])

    op.create_table(
        "case_quote_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quote_lines", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_case_quote_snapshot_case_id_created_at", "case_quote_snapshot", ["case_id", "created_at"])

    now = datetime.now(timezone.utc)
    case_source = sa.table(
        "case_source",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_system", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        case_source,
        [
            {
                "id": uuid.uuid4(),
                "name": name,
                "sort_order": idx,
                "is_system": True,
                "created_at": now,
                "updated_at": now,
            }
            for idx, name in enumerate(_DEFAULT_SOURCES)
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_case_quote_snapshot_case_id_created_at", table_name="case_quote_snapshot")
    op.drop_table("case_quote_snapshot")
    op.drop_index("ix_case_source_id", table_name="case")
    op.drop_column("case", "source_id")
    op.drop_table("case_source")

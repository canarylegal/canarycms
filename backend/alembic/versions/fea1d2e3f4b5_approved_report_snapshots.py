"""Append-only approved report artifacts. Never backfill historical approvals."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fea1d2e3f4b5"
down_revision = "fea0d1e2f3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_report_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "previous_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_report_snapshot.id", ondelete="RESTRICT"),
        ),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("archive_sha256", sa.String(64), nullable=False),
        sa.Column("archive_bytes", sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint(
            "source_kind", "source_id", "version", name="uq_financial_snapshot_version"
        ),
        sa.CheckConstraint("version > 0", name="ck_financial_snapshot_version"),
        sa.CheckConstraint(
            "source_kind IN ('firm','bank')", name="ck_financial_snapshot_source"
        ),
    )
    op.execute("""CREATE FUNCTION prevent_financial_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'Approved financial snapshots are immutable; append a new approval version';
        END $$""")
    op.execute(
        """CREATE TRIGGER immutable_financial_snapshot_rows BEFORE UPDATE OR DELETE
        ON financial_report_snapshot FOR EACH ROW EXECUTE FUNCTION prevent_financial_snapshot_mutation()"""
    )
    op.execute(
        """CREATE TRIGGER immutable_financial_snapshot_truncate BEFORE TRUNCATE
        ON financial_report_snapshot FOR EACH STATEMENT EXECUTE FUNCTION prevent_financial_snapshot_mutation()"""
    )


def downgrade():
    raise RuntimeError(
        "Approved financial evidence must be retained; roll forward instead."
    )

"""Atomic authenticator replay protection; no historical codes are recoverable."""
from alembic import op
import sqlalchemy as sa
revision = "feaac1d2e3f4"
down_revision = "fea9c0d1e2f3"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("totp_replay_state",
        sa.Column("factor_id", sa.String(64), primary_key=True),
        sa.Column("last_step", sa.BigInteger(), nullable=False))

def downgrade():
    op.drop_table("totp_replay_state")

"""Persist upload receipts independently of document deletion."""
from alembic import op
import sqlalchemy as sa
revision = 'fe4d5e6f7a8b'
down_revision = 'fe3c4d5e6f7a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('upload_receipt', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('response', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('upload_receipt')

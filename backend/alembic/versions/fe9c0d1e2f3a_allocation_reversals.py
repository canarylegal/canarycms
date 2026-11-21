"""Retain allocation history and durable reversal requests."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'fe9c0d1e2f3a'
down_revision = 'fe8b9c0d1e2f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('invoice_allocation_reversal',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('allocation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('case_invoice_allocation.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('idempotency_key', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('reversed_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('allocation_id', name='uq_allocation_reversal_original'),
        sa.UniqueConstraint('actor_user_id', 'idempotency_key', name='uq_allocation_reversal_request'),
        sa.CheckConstraint('length(trim(reason)) > 0', name='ck_allocation_reversal_reason'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM invoice_allocation_reversal LIMIT 1')).first():
        raise RuntimeError('Allocation corrections must be retained; restore a coordinated backup instead of downgrading.')
    op.drop_table('invoice_allocation_reversal')

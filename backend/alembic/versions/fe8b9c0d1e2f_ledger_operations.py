"""Durable ledger retries and reversal links.

Revision ID: fe8b9c0d1e2f
Revises: fe7a8b9c0d1e
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'fe8b9c0d1e2f'
down_revision = 'fe7a8b9c0d1e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_inter_matter_journal_from_pair_id', 'inter_matter_journal', ['from_pair_id'])
    op.create_index('ix_inter_matter_journal_to_pair_id', 'inter_matter_journal', ['to_pair_id'])
    op.create_table('ledger_operation',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('request_key', postgresql.UUID(as_uuid=True)),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('result_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('reverses_id', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('actor_user_id', 'request_key', name='uq_ledger_operation_request'),
        sa.UniqueConstraint('kind', 'reverses_id', name='uq_ledger_operation_reversal'))
    op.create_index('ix_ledger_operation_result_id', 'ledger_operation', ['result_id'])
    op.create_index('ix_ledger_operation_reverses_id', 'ledger_operation', ['reverses_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM ledger_operation LIMIT 1')).first():
        raise RuntimeError('Ledger operation receipts must be retained; restore a coordinated backup instead of downgrading.')
    op.drop_table('ledger_operation')
    op.drop_index('ix_inter_matter_journal_to_pair_id', table_name='inter_matter_journal')
    op.drop_index('ix_inter_matter_journal_from_pair_id', table_name='inter_matter_journal')

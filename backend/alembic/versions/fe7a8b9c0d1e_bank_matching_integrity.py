"""Version bank edits and prevent duplicate payment matching without rewriting data."""
from alembic import op
import sqlalchemy as sa
revision = 'fe7a8b9c0d1e'
down_revision = 'fe6f7a8b9c0d'
branch_labels = None
depends_on = None
TOTAL_COLUMNS = {
    'bank_reconciliation': ['statement_balance_pence', 'ledger_total_pence', 'unpresented_total_pence',
                           'unmatched_statement_total_pence', 'difference_pence'],
    'client_account_reconciliation': ['ledger_client_total_pence', 'ledger_office_total_pence',
                                      'bank_statement_balance_pence', 'difference_pence'],
}


def upgrade():
    duplicates = op.get_bind().execute(sa.text('SELECT matched_pair_id FROM bank_statement_line WHERE matched_pair_id IS NOT NULL GROUP BY matched_pair_id HAVING count(*) > 1 LIMIT 1')).first()
    if duplicates:
        raise RuntimeError('Duplicate historical bank matches require review before upgrading; no records have been rewritten.')
    for table, columns in TOTAL_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)
    op.add_column('bank_statement_line', sa.Column('version', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('bank_reconciliation', sa.Column('version', sa.Integer(), nullable=False, server_default='0'))
    op.create_unique_constraint('uq_statement_matched_pair', 'bank_statement_line', ['matched_pair_id'])
    op.execute('ALTER TABLE bank_statement_line ADD CONSTRAINT ck_statement_match_state CHECK (NOT (ignored AND matched_pair_id IS NOT NULL)) NOT VALID')


def downgrade():
    # Refuse narrowing if any totals exceed int32; PostgreSQL preserves data transactionally.
    for table, columns in TOTAL_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False)
    op.drop_constraint('ck_statement_match_state', 'bank_statement_line', type_='check')
    op.drop_constraint('uq_statement_matched_pair', 'bank_statement_line', type_='unique')
    op.drop_column('bank_reconciliation', 'version')
    op.drop_column('bank_statement_line', 'version')

"""Allocation request identity and positive-value guard; do not rewrite historical data."""
from alembic import op
import sqlalchemy as sa
revision = 'fe6f7a8b9c0d'
down_revision = 'fe5e6f7a8b9c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('case_invoice_allocation', sa.Column('idempotency_key', sa.Uuid(), nullable=True))
    op.create_unique_constraint('uq_invoice_allocation_request', 'case_invoice_allocation', ['invoice_id','idempotency_key'])
    # Enforce future writes without silently repairing or rejecting legacy rows during upgrade.
    op.execute('ALTER TABLE case_invoice_allocation ADD CONSTRAINT ck_invoice_allocation_positive CHECK (amount_pence > 0) NOT VALID')


def downgrade():
    op.drop_constraint('ck_invoice_allocation_positive', 'case_invoice_allocation', type_='check')
    op.drop_constraint('uq_invoice_allocation_request', 'case_invoice_allocation', type_='unique')
    op.drop_column('case_invoice_allocation','idempotency_key')

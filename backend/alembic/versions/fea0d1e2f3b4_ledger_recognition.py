"""Record ledger recognition time without rewriting posting history.

Revision ID: fea0d1e2f3b4
Revises: fe9c0d1e2f3a
"""
from alembic import op
import sqlalchemy as sa

revision = 'fea0d1e2f3b4'
down_revision = 'fe9c0d1e2f3a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ledger_entry', sa.Column('recognised_at', sa.DateTime(timezone=True), nullable=True))
    # Recover authoritative evidence where it exists. Unknown legacy approval times
    # remain NULL and retain the recorded posting date, rather than inventing a time.
    op.execute('''UPDATE ledger_entry e SET recognised_at = GREATEST(e.posted_at, evidence.at)
        FROM (SELECT entity_id, MIN(created_at) AS at FROM audit_event
              WHERE action = 'ledger.approve' AND entity_type = 'ledger_pair'
              GROUP BY entity_id) evidence
        WHERE e.pair_id::text = evidence.entity_id AND e.is_approved AND NOT e.is_anticipated''')
    op.execute('''UPDATE ledger_entry e SET recognised_at = GREATEST(e.posted_at, i.approved_at)
        FROM case_invoice i WHERE e.pair_id = i.ledger_pair_id
        AND i.approved_at IS NOT NULL AND e.is_approved AND NOT e.is_anticipated''')


def downgrade():
    # Removing recognition history would silently alter past financial reports.
    raise RuntimeError('Ledger recognition history must be retained; roll forward instead.')

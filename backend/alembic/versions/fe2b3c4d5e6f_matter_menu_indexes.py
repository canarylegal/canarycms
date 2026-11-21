"""Indexes for bounded matter-menu traversal and common saved filters."""
from alembic import op

revision = 'fe2b3c4d5e6f'
down_revision = 'fe1a2b3c4d5e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_case_menu_created', 'case', ['created_at', 'id'])
    op.create_index('ix_case_menu_status', 'case', ['status', 'created_at', 'id'])
    op.create_index('ix_case_menu_fee_earner', 'case', ['fee_earner_user_id', 'created_at', 'id'])


def downgrade():
    for name in ('ix_case_menu_fee_earner', 'ix_case_menu_status', 'ix_case_menu_created'):
        op.drop_index(name, table_name='case')

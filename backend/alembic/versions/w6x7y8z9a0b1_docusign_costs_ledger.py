"""DocuSign envelope costs and signing-request ledger link."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "w6x7y8z9a0b1"
down_revision = "v5w6x7y8z9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "docusign_integration_settings",
        sa.Column("cost_standard_pence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "docusign_integration_settings",
        sa.Column("cost_wes_pence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "docusign_integration_settings",
        sa.Column("cost_qes_pence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "docusign_signing_request",
        sa.Column("ledger_pair_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("docusign_signing_request", "ledger_pair_id")
    op.drop_column("docusign_integration_settings", "cost_qes_pence")
    op.drop_column("docusign_integration_settings", "cost_wes_pence")
    op.drop_column("docusign_integration_settings", "cost_standard_pence")

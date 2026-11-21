"""Immutable correction of an allocation; the original allocation is retained."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.timeutil import utcnow


class InvoiceAllocationReversal(Base):
    __tablename__ = 'invoice_allocation_reversal'
    __table_args__ = (
        UniqueConstraint('allocation_id', name='uq_allocation_reversal_original'),
        UniqueConstraint('actor_user_id', 'idempotency_key', name='uq_allocation_reversal_request'),
        CheckConstraint("length(trim(reason)) > 0", name='ck_allocation_reversal_reason'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    allocation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey('case_invoice_allocation.id', ondelete='RESTRICT'), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('user.id'), nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reversed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

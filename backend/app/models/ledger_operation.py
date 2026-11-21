"""Durable request receipts and immutable links to compensating postings."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.timeutil import utcnow


class LedgerOperation(Base):
    __tablename__ = 'ledger_operation'
    __table_args__ = (
        UniqueConstraint('actor_user_id', 'request_key', name='uq_ledger_operation_request'),
        UniqueConstraint('kind', 'reverses_id', name='uq_ledger_operation_reversal'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('user.id'), nullable=False)
    request_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

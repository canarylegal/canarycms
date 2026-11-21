"""Append-only approval artifacts; bytes live in the same transaction as approval."""

import uuid
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.timeutil import utcnow


class FinancialReportSnapshot(Base):
    __tablename__ = "financial_report_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "source_kind", "source_id", "version", name="uq_financial_snapshot_version"
        ),
        CheckConstraint("version > 0", name="ck_financial_snapshot_version"),
        CheckConstraint(
            "source_kind IN ('firm', 'bank')", name="ck_financial_snapshot_source"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_report_snapshot.id", ondelete="RESTRICT"),
    )
    approved_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    approved_at = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    archive_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

"""SQLAlchemy models — fee_scale domain."""
from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    LargeBinary,
    Time,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

class FeeScale(Base):
    """Firm-wide fee scale templates used when composing quotes."""

    __tablename__ = "fee_scale"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    vat_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    # Scope: (NULL,NULL) = all cases; (H,NULL) = all sub-types under head H; (H,S) = one sub-type.
    matter_head_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_head_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    matter_sub_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matter_sub_type.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("reference", name="uq_fee_scale_reference"),)

class UserFeeScaleFavorite(Base):
    """Per-user starred fee scales for quick quote selection."""

    __tablename__ = "user_fee_scale_favorite"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fee_scale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "fee_scale_id", name="uq_user_fee_scale_favorite"),)

class FeeScaleLineKind(str, enum.Enum):
    section_header = "section_header"
    item = "item"
    vat = "vat"
    subtotal = "subtotal"
    total = "total"

class FeeScaleAmountKind(str, enum.Enum):
    fixed = "fixed"
    editable = "editable"
    band = "band"

class FeeScaleVatTreatment(str, enum.Enum):
    """How VAT applies to a line item amount."""

    included = "included"  # Including / No VAT — amount is final; no separate VAT column
    plus_vat = "plus_vat"  # Plus VAT — amount is net; VAT shown in VAT column

class FeeScaleCategory(Base):
    __tablename__ = "fee_scale_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fee_scale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class FeeScaleBandSet(Base):
    __tablename__ = "fee_scale_band_set"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fee_scale_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class FeeScaleBandRow(Base):
    __tablename__ = "fee_scale_band_row"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    band_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale_band_set.id", ondelete="CASCADE"), nullable=False, index=True
    )
    min_value_pence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_value_pence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    amount_pence: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class FeeScaleLine(Base):
    __tablename__ = "fee_scale_line"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale_category.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    line_kind: Mapped[FeeScaleLineKind] = mapped_column(
        Enum(FeeScaleLineKind, name="fee_scale_line_kind"), nullable=False
    )
    amount_kind: Mapped[FeeScaleAmountKind | None] = mapped_column(
        Enum(FeeScaleAmountKind, name="fee_scale_amount_kind"), nullable=True
    )
    default_amount_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    band_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_scale_band_set.id", ondelete="SET NULL"), nullable=True
    )
    vat_treatment: Mapped[FeeScaleVatTreatment] = mapped_column(
        Enum(FeeScaleVatTreatment, name="fee_scale_vat_treatment"),
        nullable=False,
        default=FeeScaleVatTreatment.included,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

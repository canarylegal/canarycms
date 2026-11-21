import uuid
from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class DocumentRecovery(Base):
    __tablename__ = 'document_recovery'
    # No file FK: recovery must survive deleting the live File row.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    kind: Mapped[str] = mapped_column(String(24))
    snapshot: Mapped[dict] = mapped_column(JSON)
    storage_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

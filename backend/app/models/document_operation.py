import uuid
from sqlalchemy import JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class DocumentOperation(Base):
    __tablename__ = "document_operation"
    # No file FK: deletion must not erase retry history.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)

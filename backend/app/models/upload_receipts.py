import uuid
from sqlalchemy import JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class UploadReceipt(Base):
    __tablename__ = 'upload_receipt'
    # Deliberately no file FK: deleting a document must not permit a replay to recreate it.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)


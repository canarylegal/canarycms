"""Local, provider-independent hosted integration state. No existing settings are migrated."""
import uuid
from sqlalchemy import Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CommercialConnection(Base):
    __tablename__ = "commercial_connection"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, unique=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    origin: Mapped[str | None] = mapped_column(Text)
    secret_enc: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CommercialCredential(Base):
    __tablename__ = "commercial_credential"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    secret_enc: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class CommercialOperation(Base):
    __tablename__ = "commercial_operation"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    installation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    adapter: Mapped[str] = mapped_column(String(80), nullable=False)
    credential_key: Mapped[str] = mapped_column(String(80), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_enc: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    credential_version: Mapped[int | None] = mapped_column(Integer)
    result_enc: Mapped[str | None] = mapped_column(Text)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(40))


class CommercialApplication(Base):
    __tablename__ = "commercial_application"
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)

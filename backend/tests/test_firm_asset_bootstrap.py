"""Firm branding asset seed bootstrap."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

import app.file_storage as file_storage
from app.firm_asset_bootstrap import sync_firm_assets_from_seed
from app.models import Base, File as DbFile, FileCategory, FirmSettings, User, UserRole


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            DbFile.__table__,
            FirmSettings.__table__,
        ],
    )
    for column, original in patched:
        column.type = original
    return sessionmaker(bind=engine)()


def _admin(db: Session) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email="asset.seed@example.com",
        password_hash="x",
        display_name="Asset Seed Admin",
        initials="ASA",
        role=UserRole.admin,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def test_sync_firm_assets_seeds_when_empty(tmp_path: Path, monkeypatch) -> None:
    assets = tmp_path / "assets"
    (assets / "letterheads").mkdir(parents=True)
    (assets / "logos").mkdir(parents=True)
    letterhead = assets / "letterheads" / "letterhead.docx"
    letterhead.write_bytes(b"PK\x03\x04fake-docx")
    logo = assets / "logos" / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    files = tmp_path / "files"
    files.mkdir()
    monkeypatch.setenv("FIRM_ASSETS_SEED_DIR", str(assets))
    monkeypatch.setattr(file_storage, "FILES_ROOT", files.resolve())

    db = _session()
    _admin(db)
    assert sync_firm_assets_from_seed(db) == 2
    row = db.get(FirmSettings, 1)
    assert row is not None
    assert row.letterhead_file_id is not None
    assert row.portal_logo_file_id is not None

    # Idempotent — does not clobber
    assert sync_firm_assets_from_seed(db) == 0
    row2 = db.get(FirmSettings, 1)
    assert row2.letterhead_file_id == row.letterhead_file_id
    assert row2.portal_logo_file_id == row.portal_logo_file_id


def test_sync_firm_assets_skips_when_already_set(tmp_path: Path, monkeypatch) -> None:
    assets = tmp_path / "assets"
    (assets / "letterheads").mkdir(parents=True)
    (assets / "letterheads" / "letterhead.docx").write_bytes(b"PK\x03\x04fake")
    files = tmp_path / "files"
    files.mkdir()
    monkeypatch.setenv("FIRM_ASSETS_SEED_DIR", str(assets))
    monkeypatch.setattr(file_storage, "FILES_ROOT", files.resolve())

    db = _session()
    admin = _admin(db)
    existing = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db.add(
        DbFile(
            id=existing,
            case_id=None,
            owner_id=admin.id,
            category=FileCategory.firm_letterhead,
            storage_path="firm/letterhead/existing.docx",
            folder_path="",
            parent_file_id=None,
            is_pinned=False,
            original_filename="existing.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=1,
            version=1,
            checksum=None,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(FirmSettings(id=1, letterhead_file_id=existing))
    db.flush()

    assert sync_firm_assets_from_seed(db) == 0
    assert db.get(FirmSettings, 1).letterhead_file_id == existing

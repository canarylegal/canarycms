"""Firm default signature fallback for fee earner merge code."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from app.docx_util import fee_earner_signature_for_merge, signature_width_inches_from_scale
from app.file_storage import FILES_ROOT, ensure_files_root
from app.models import Base, File, FileCategory, FirmSettings, User, UserRole

# Minimal valid 1x1 PNG.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def sig_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CANARY_FILES_ROOT", str(tmp_path / "files"))
    ensure_files_root()

    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()

    for table in (User.__table__, File.__table__, FirmSettings.__table__):
        table.create(engine)

    for column, original in patched:
        column.type = original

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _add_user(db, *, signature_file_id: uuid.UUID | None = None) -> User:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"user-{uid.hex[:8]}@example.com",
        password_hash="x",
        display_name="Test User",
        initials=f"U{uid.hex[:4].upper()}",
        role=UserRole.admin,
        signature_file_id=signature_file_id,
        signature_scale=7,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_signature_file(db, owner_id: uuid.UUID, *, rel_path: str) -> File:
    fid = uuid.uuid4()
    row = File(
        id=fid,
        case_id=None,
        owner_id=owner_id,
        category=FileCategory.firm_default_signature,
        storage_path=rel_path,
        folder_path="",
        is_pinned=False,
        original_filename="sig.png",
        mime_type="image/png",
        size_bytes=len(_TINY_PNG),
        version=1,
        checksum=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_fee_earner_signature_falls_back_to_firm_default(sig_db) -> None:
    admin = _add_user(sig_db)
    fee_earner = _add_user(sig_db)

    rel = "firm/default-signature/test.png"
    abs_path = FILES_ROOT / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(_TINY_PNG)
    sig_file = _add_signature_file(sig_db, admin.id, rel_path=rel)

    firm = FirmSettings(
        id=1,
        trading_name="Test Firm",
        default_signature_file_id=sig_file.id,
        default_signature_scale=10,
    )
    sig_db.add(firm)
    sig_db.commit()

    info = fee_earner_signature_for_merge(sig_db, fee_earner.id)
    assert info is not None
    path, width = info
    assert path == abs_path.resolve()
    assert width == pytest.approx(signature_width_inches_from_scale(10))


def test_user_signature_takes_priority_over_firm_default(sig_db) -> None:
    admin = _add_user(sig_db)
    fee_earner = _add_user(sig_db)

    firm_rel = "firm/default-signature/firm.png"
    firm_abs = FILES_ROOT / firm_rel
    firm_abs.parent.mkdir(parents=True, exist_ok=True)
    firm_abs.write_bytes(_TINY_PNG)
    firm_sig = _add_signature_file(sig_db, admin.id, rel_path=firm_rel)

    user_rel = "users/signatures/user.png"
    user_abs = FILES_ROOT / user_rel
    user_abs.parent.mkdir(parents=True, exist_ok=True)
    user_abs.write_bytes(_TINY_PNG)
    user_sig = _add_signature_file(sig_db, fee_earner.id, rel_path=user_rel)
    fee_earner.signature_file_id = user_sig.id
    fee_earner.signature_scale = 3
    sig_db.add(fee_earner)

    firm = FirmSettings(
        id=1,
        trading_name="Test Firm",
        default_signature_file_id=firm_sig.id,
        default_signature_scale=10,
    )
    sig_db.add(firm)
    sig_db.commit()

    info = fee_earner_signature_for_merge(sig_db, fee_earner.id)
    assert info is not None
    path, width = info
    assert path == user_abs.resolve()
    assert width == pytest.approx(signature_width_inches_from_scale(3))

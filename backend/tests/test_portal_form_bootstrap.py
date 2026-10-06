"""Firm portal-forms seed bootstrap."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Base,
    MatterHeadType,
    MatterSubType,
    PortalFormTemplate,
    PortalFormTemplateField,
    User,
    UserRole,
)
from app.portal_form_bootstrap import sync_portal_forms_from_seed


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
            MatterHeadType.__table__,
            MatterSubType.__table__,
            PortalFormTemplate.__table__,
            PortalFormTemplateField.__table__,
        ],
    )
    for column, original in patched:
        column.type = original
    return sessionmaker(bind=engine)()


def test_sync_portal_forms_from_seed_creates_missing(tmp_path: Path) -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash="x",
        display_name="Admin",
        initials="AD",
        role=UserRole.admin,
        is_active=True,
    )
    head = MatterHeadType(id=uuid.uuid4(), name="Conveyancing, Residential", created_at=now, updated_at=now)
    sub = MatterSubType(
        id=uuid.uuid4(),
        head_type_id=head.id,
        name="Purchase",
        prefix="Purchase of",
        created_at=now,
        updated_at=now,
    )
    db.add_all([admin, head, sub])
    db.commit()

    manifest = {
        "version": 1,
        "templates": [
            {
                "reference": "example_purchase_info",
                "name": "Example Purchase Info",
                "description": "Illustrative",
                "scope": "residential_purchase",
                "fields": [
                    {
                        "field_key": "full_name",
                        "label": "Full name",
                        "field_type": "text",
                        "required": True,
                        "sort_order": 0,
                        "select_options": [],
                    }
                ],
            },
            {
                "reference": "example_global",
                "name": "Example Global",
                "scope": "global",
                "fields": [
                    {
                        "field_key": "notes",
                        "label": "Notes",
                        "field_type": "textarea",
                        "required": False,
                        "sort_order": 0,
                        "select_options": [],
                    }
                ],
            },
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    n = sync_portal_forms_from_seed(db, seed_dir=tmp_path)
    assert n == 2
    refs = {
        r
        for (r,) in db.execute(select(PortalFormTemplate.reference)).all()
    }
    assert refs == {"example_purchase_info", "example_global"}
    purchase = db.execute(
        select(PortalFormTemplate).where(PortalFormTemplate.reference == "example_purchase_info")
    ).scalar_one()
    assert purchase.matter_head_type_id == head.id
    assert purchase.matter_sub_type_id == sub.id

    # Idempotent
    assert sync_portal_forms_from_seed(db, seed_dir=tmp_path) == 0

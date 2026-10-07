"""Firm fee-scale seed bootstrap."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.fee_scale_bootstrap import sync_fee_scales_from_seed
from app.models import (
    Base,
    FeeScale,
    FeeScaleBandSet,
    FeeScaleCategory,
    FeeScaleLine,
    MatterHeadType,
    MatterSubType,
    User,
    UserRole,
)


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
            FeeScale.__table__,
            FeeScaleCategory.__table__,
            FeeScaleBandSet.__table__,
            FeeScaleLine.__table__,
        ],
    )
    # FeeScaleBandRow needed for apply
    from app.models import FeeScaleBandRow

    FeeScaleBandRow.__table__.create(bind=engine, checkfirst=True)
    for column, original in patched:
        column.type = original
    return sessionmaker(bind=engine)()


def _seed_admin_and_types(db: Session) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        User(
            id=uuid.uuid4(),
            email="fee.seed@example.com",
            password_hash="x",
            display_name="Fee Seed Admin",
            initials="FSA",
            role=UserRole.admin,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    head = MatterHeadType(
        id=uuid.uuid4(),
        name="Conveyancing, Residential",
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    db.add(head)
    db.flush()
    db.add(
        MatterSubType(
            id=uuid.uuid4(),
            head_type_id=head.id,
            name="Purchase",
            prefix="Purchase of",
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()


def test_sync_fee_scales_from_seed_creates_with_bands(tmp_path: Path, monkeypatch) -> None:
    seed = tmp_path / "fee-scales"
    seed.mkdir()
    (seed / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "scales": [
                    {
                        "reference": "EXAMPLE_RESIDENTIAL_PURCHASE",
                        "name": "Example purchase",
                        "scope": "residential_purchase",
                        "band_sets": [
                            {
                                "key": "legal_fee",
                                "name": "Legal fee",
                                "rows": [
                                    {"min_value_pence": 0, "max_value_pence": 100, "amount_pence": 50},
                                    {"min_value_pence": 101, "max_value_pence": None, "amount_pence": 75},
                                ],
                            }
                        ],
                        "categories": [
                            {
                                "name": "Fees",
                                "lines": [
                                    {
                                        "name": "Legal fee",
                                        "line_kind": "item",
                                        "amount_kind": "band",
                                        "band_set_key": "legal_fee",
                                        "vat_treatment": "plus_vat",
                                    },
                                    {"name": "Total", "line_kind": "total"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FEE_SCALES_SEED_DIR", str(seed))
    db = _session()
    _seed_admin_and_types(db)

    assert sync_fee_scales_from_seed(db) == 1
    scale = db.execute(select(FeeScale).where(FeeScale.reference == "EXAMPLE_RESIDENTIAL_PURCHASE")).scalar_one()
    assert scale.name == "Example purchase"
    assert db.execute(select(FeeScaleBandSet).where(FeeScaleBandSet.fee_scale_id == scale.id)).scalars().first()
    assert db.execute(select(FeeScaleLine)).scalars().first() is not None

    # Idempotent
    assert sync_fee_scales_from_seed(db) == 0

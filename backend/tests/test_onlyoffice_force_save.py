"""ONLYOFFICE arm/wait save helpers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.onlyoffice_force_save import oo_force_save_arm, oo_force_save_wait
from app.models import File as DbFile


@pytest.mark.asyncio
async def test_oo_force_save_wait_succeeds_when_version_increases() -> None:
    row = DbFile(id=uuid.uuid4(), version=2, oo_force_save_pending=True)
    db = MagicMock()

    def refresh(r: DbFile) -> None:
        r.version = 3

    db.refresh.side_effect = refresh

    with patch("app.onlyoffice_force_save.asyncio.sleep", new_callable=AsyncMock):
        await oo_force_save_wait(db, row, base_version=2, timeout_loops=3)

    assert row.oo_force_save_pending is False


@pytest.mark.asyncio
async def test_oo_force_save_wait_fails_when_version_unchanged() -> None:
    row = DbFile(id=uuid.uuid4(), version=2, oo_force_save_pending=True)
    db = MagicMock()

    with patch("app.onlyoffice_force_save.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await oo_force_save_wait(db, row, base_version=2, timeout_loops=2)
    assert exc.value.status_code == 422
    assert row.oo_force_save_pending is False


def test_oo_force_save_arm_sets_pending() -> None:
    row = DbFile(id=uuid.uuid4(), version=4, oo_force_save_pending=False)
    db = MagicMock()
    base = oo_force_save_arm(db, row)
    assert base == 4
    assert row.oo_force_save_pending is True
    db.commit.assert_called_once()

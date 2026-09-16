"""ONLYOFFICE arm/wait/command save helpers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.onlyoffice_force_save import (
    oo_force_save_arm,
    oo_force_save_issue_command,
    oo_force_save_wait,
)
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


def _mock_async_client(post_resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.post = AsyncMock(return_value=post_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_oo_force_save_issue_command_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "unit-test-secret")
    monkeypatch.setenv("ONLYOFFICE_DS_INTERNAL_URL", "http://onlyoffice-test")
    row = DbFile(id=uuid.uuid4(), version=1, oo_force_save_pending=False)
    db = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"error": 0}
    client = _mock_async_client(resp)

    with patch("app.onlyoffice_force_save.httpx.AsyncClient", return_value=client):
        await oo_force_save_issue_command(db, row, doc_key="key-1", file_id=row.id)

    assert row.oo_force_save_pending is True
    db.commit.assert_called()
    client.post.assert_awaited_once()
    posted_url = client.post.await_args.args[0]
    assert posted_url.endswith("/coauthoring/CommandService.ashx")
    assert "onlyoffice-test" in posted_url


@pytest.mark.asyncio
async def test_oo_force_save_issue_command_error_4_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "unit-test-secret")
    row = DbFile(id=uuid.uuid4(), version=1, oo_force_save_pending=True)
    db = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"error": 4}

    with patch("app.onlyoffice_force_save.httpx.AsyncClient", return_value=_mock_async_client(resp)):
        await oo_force_save_issue_command(db, row, doc_key="key-2", file_id=row.id)

    assert row.oo_force_save_pending is True


@pytest.mark.asyncio
async def test_oo_force_save_issue_command_nonzero_error_raises_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "unit-test-secret")
    row = DbFile(id=uuid.uuid4(), version=1, oo_force_save_pending=True)
    db = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"error": 1}

    with patch("app.onlyoffice_force_save.httpx.AsyncClient", return_value=_mock_async_client(resp)):
        with pytest.raises(HTTPException) as exc:
            await oo_force_save_issue_command(db, row, doc_key="key-3", file_id=row.id)
    assert exc.value.status_code == 502
    assert row.oo_force_save_pending is False


@pytest.mark.asyncio
async def test_oo_force_save_issue_command_http_failure_raises_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "unit-test-secret")
    row = DbFile(id=uuid.uuid4(), version=1, oo_force_save_pending=True)
    db = MagicMock()

    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.onlyoffice_force_save.httpx.AsyncClient", return_value=client):
        with pytest.raises(HTTPException) as exc:
            await oo_force_save_issue_command(db, row, doc_key="key-4", file_id=row.id)
    assert exc.value.status_code == 502
    assert row.oo_force_save_pending is False

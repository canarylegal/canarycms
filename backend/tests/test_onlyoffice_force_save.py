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
async def test_oo_force_save_wait_requires_matching_confirmation() -> None:
    attempt = uuid.uuid4()
    row = DbFile(id=uuid.uuid4(), version=2, oo_force_save_pending=True,
                 oo_save_attempt_id=attempt, oo_save_base_version=2, oo_save_state="pending")
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row

    def refresh(r: DbFile) -> None:
        r.version = 3
        r.oo_save_state = "confirmed"
        r.oo_force_save_pending = False

    db.refresh.side_effect = refresh

    with patch("app.onlyoffice_force_save.asyncio.sleep", new_callable=AsyncMock):
        await oo_force_save_wait(db, row, base_version=2, timeout_loops=3, attempt_id=attempt)

    assert row.oo_force_save_pending is False


@pytest.mark.asyncio
async def test_oo_force_save_wait_fails_when_version_unchanged() -> None:
    attempt = uuid.uuid4()
    row = DbFile(id=uuid.uuid4(), version=2, oo_force_save_pending=True,
                 oo_save_attempt_id=attempt, oo_save_base_version=2, oo_save_state="pending")
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row

    with patch("app.onlyoffice_force_save.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await oo_force_save_wait(db, row, base_version=2, timeout_loops=2, attempt_id=attempt)
    assert exc.value.status_code == 422
    assert row.oo_save_state == "pending"  # timeout is not evidence of success or failure


def test_oo_force_save_arm_sets_pending() -> None:
    row = DbFile(id=uuid.uuid4(), version=4, oo_force_save_pending=False)
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
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
    db.execute.return_value.scalar_one_or_none.return_value = row
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
    assert client.post.await_args.kwargs["json"]["userdata"] == str(row.oo_save_attempt_id)


@pytest.mark.asyncio
async def test_oo_force_save_issue_command_error_4_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "unit-test-secret")
    row = DbFile(id=uuid.uuid4(), version=1, oo_force_save_pending=True)
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"error": 4}

    with patch("app.onlyoffice_force_save.httpx.AsyncClient", return_value=_mock_async_client(resp)):
        await oo_force_save_issue_command(db, row, doc_key="key-2", file_id=row.id)

    assert row.oo_force_save_pending is False
    assert row.oo_save_state == "failed"
    assert row.version == 1


@pytest.mark.asyncio
async def test_oo_force_save_issue_command_nonzero_error_raises_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "unit-test-secret")
    row = DbFile(id=uuid.uuid4(), version=1, oo_force_save_pending=True)
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
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
    db.execute.return_value.scalar_one_or_none.return_value = row

    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.onlyoffice_force_save.httpx.AsyncClient", return_value=client):
        with pytest.raises(HTTPException) as exc:
            await oo_force_save_issue_command(db, row, doc_key="key-4", file_id=row.id)
    assert exc.value.status_code == 502
    assert row.oo_force_save_pending is False


@pytest.mark.asyncio
async def test_legacy_wait_does_not_adopt_a_newer_attempt():
    from app.onlyoffice_force_save import oo_force_save_command_service
    attempt = uuid.uuid4()
    row = DbFile(id=uuid.uuid4(), version=1, oo_save_attempt_id=attempt,
                 oo_save_base_version=1, oo_save_state='pending')
    db = MagicMock()
    async def newer_attempt(*args, **kwargs):
        row.oo_save_attempt_id = uuid.uuid4()
        row.oo_save_state = 'confirmed'
        row.version = 2
    with patch('app.onlyoffice_force_save.oo_force_save_issue_command', side_effect=newer_attempt), \
         patch('app.onlyoffice_force_save.asyncio.sleep', new_callable=AsyncMock):
        with pytest.raises(HTTPException):
            await oo_force_save_command_service(db, row, doc_key='key', file_id=row.id, attempt_id=attempt)

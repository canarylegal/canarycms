"""Tests for Outlook pending compose handoff queue (web → add-in)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routers import outlook_plugin as outlook_plugin_router
from app.schemas import OutlookPluginPendingComposeHandoffPutIn
from app.security import create_compose_handoff_token


def _handoff_token(user_id: uuid.UUID, case_id: uuid.UUID) -> str:
    return create_compose_handoff_token(
        user_id=str(user_id),
        case_id=str(case_id),
        to="client@example.com",
        subject="Quote",
        body="Please find attached.",
        attachment_file_ids=[str(uuid.uuid4())],
    )


class _FakeDb:
    def __init__(self, row: SimpleNamespace) -> None:
        self.row = row
        self.commits = 0

    def get(self, _model, _id):
        return self.row

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, _row) -> None:
        return None


def _user_row(user_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        outlook_pending_compose_handoff_token=None,
        outlook_pending_compose_handoff_expires_at=None,
        updated_at=datetime.now(timezone.utc),
    )


def test_put_and_claim_pending_compose_handoff(monkeypatch) -> None:
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)
    row = _user_row(user_id)
    db = _FakeDb(row)

    def fake_require_case_access(cid, _user, _db):
        assert cid == case_id

    monkeypatch.setattr(outlook_plugin_router, "require_case_access", fake_require_case_access)

    token = _handoff_token(user_id, case_id)
    put_in = OutlookPluginPendingComposeHandoffPutIn(handoff_token=token, ttl_seconds=3600)
    out = outlook_plugin_router.outlook_plugin_put_pending_compose_handoff(put_in, user, db)
    assert out.active is True
    assert out.handoff_token == token
    assert out.case_id == case_id
    assert row.outlook_pending_compose_handoff_token == token
    assert row.outlook_pending_compose_handoff_expires_at is not None

    claimed = outlook_plugin_router.outlook_plugin_claim_pending_compose_handoff(user, db)
    assert claimed.active is True
    assert claimed.handoff_token == token
    assert claimed.case_id == case_id
    assert row.outlook_pending_compose_handoff_token is None

    empty = outlook_plugin_router.outlook_plugin_claim_pending_compose_handoff(user, db)
    assert empty.active is False


def test_expired_pending_compose_handoff_is_cleared(monkeypatch) -> None:
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)
    row = _user_row(user_id)
    row.outlook_pending_compose_handoff_token = _handoff_token(user_id, case_id)
    row.outlook_pending_compose_handoff_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db = _FakeDb(row)

    monkeypatch.setattr(outlook_plugin_router, "require_case_access", lambda *_a, **_k: None)

    claimed = outlook_plugin_router.outlook_plugin_claim_pending_compose_handoff(user, db)
    assert claimed.active is False
    assert row.outlook_pending_compose_handoff_token is None

"""Concurrent operators must not send one notification twice."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
import uuid
import pytest
from sqlalchemy import select, func
from fastapi import HTTPException
from app.db import SessionLocal
from app import notification_outbox as outbox
from app.models import NotificationOutbox, NotificationAttempt
from tests.test_notification_outbox import fixture, enqueue


def test_parallel_dispatch_claim_is_durable(db, monkeypatch):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Isolated PostgreSQL required")
    db, admin, recipient, case = fixture(db)
    row = enqueue(db, admin, recipient, case, str(uuid.uuid4()))
    db.commit()
    identity, actor = row.id, admin.id
    db.rollback()
    started, competed = Event(), Event()
    calls = []
    monkeypatch.setattr(outbox, "resolve_alert_transport", lambda db: "smtp")

    def sender(session, message):
        calls.append(message.notification_id)
        started.set()
        assert competed.wait(15)
        return "smtp"

    def run():
        return outbox.deliver(identity, actor_id=actor, sender=sender)

    def contender():
        assert started.wait(15)
        try:
            assert run()["state"] == "sending"
        finally:
            competed.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(run), pool.submit(contender)
        assert first.result(20)["state"] == "sent"
        second.result(20)
    assert calls == [str(identity)]
    assert (
        db.scalar(
            select(func.count())
            .select_from(NotificationAttempt)
            .where(NotificationAttempt.notification_id == identity)
        )
        == 1
    )


@pytest.mark.parametrize("rollback", [False, True])
def test_parallel_enqueue_is_atomic_and_retryable(db, rollback):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Isolated PostgreSQL required")
    db, admin, recipient, case = fixture(db)
    aid, rid, cid = admin.id, recipient.id, case.id
    db.rollback()
    key = str(uuid.uuid4())
    locked, attempted = Event(), Event()

    def queue(session):
        return outbox.enqueue_staff(
            session,
            kind="invoice_approved",
            event_key=key,
            case_id=cid,
            recipient_user_id=rid,
            actor_id=aid,
            context={},
        )

    def first():
        with SessionLocal() as session:
            row = queue(session)
            identity = row.id
            locked.set()
            assert attempted.wait(15)
            if rollback:
                session.rollback()
            else:
                session.commit()
            return identity

    def second():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error:
                    queue(session)
                assert error.value.status_code == 429
        finally:
            attempted.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(first), pool.submit(second)
        identity = a.result(20)
        b.result(20)
    assert (db.get(NotificationOutbox, identity) is None) == rollback
    db.rollback()
    with SessionLocal() as session:
        assert queue(session).id == identity
        session.commit()
    assert (
        db.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.id == identity)
        )
        == 1
    )


def test_seed_pending_and_uncertain_for_restart(db, monkeypatch):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Isolated PostgreSQL required")
    db, admin, recipient, case = fixture(db)
    pending = enqueue(db, admin, recipient, case, "restart-pending")
    uncertain = enqueue(db, admin, recipient, case, "restart-uncertain")
    identity, actor = uncertain.id, admin.id
    db.commit()
    db.rollback()
    monkeypatch.setattr(outbox, "resolve_alert_transport", lambda db: "smtp")

    def timeout(*args):
        raise TimeoutError("Synthetic unknown provider result")

    assert (
        outbox.deliver(identity, actor_id=actor, sender=timeout)["state"] == "uncertain"
    )

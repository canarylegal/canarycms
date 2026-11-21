"""Two form submissions cannot publish duplicate artifacts or staff notices."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import Contact, ContactType, PortalFormSubmission, NotificationOutbox
from app import portal_form_service as forms, notification_outbox as outbox
from tests.test_notification_outbox import fixture
from tests.test_remaining_staff_outbox import form_fixture


@pytest.mark.parametrize("rollback", [False, True])
def test_competing_form_completions_have_one_notice(db, monkeypatch, rollback):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Isolated PostgreSQL required")
    db, user, recipient, case = fixture(db)
    contact = Contact(
        id=uuid.uuid4(),
        type=ContactType.person,
        name="Synthetic client",
        email="synthetic@example.com",
    )
    db.add(contact)
    db.commit()
    sub = form_fixture(db, user, case, contact)
    sid, cid = sub.id, contact.id
    db.rollback()
    entered, competing = Event(), Event()
    snapshots = []

    def snapshot(*a, **kw):
        snapshots.append(1)
        if len(snapshots) == 1:
            entered.set()
            assert competing.wait(15)
        # No real external documents are used in this concurrency test.
        return SimpleNamespace(id=None)

    monkeypatch.setattr(forms, "_save_snapshot_on_matter", snapshot)
    original = outbox.log_event
    audits = []

    def audit(*a, **kw):
        audits.append(1)
        if rollback and len(audits) == 1:
            raise RuntimeError("Injected queue failure")
        return original(*a, **kw)

    monkeypatch.setattr(outbox, "log_event", audit)

    def run():
        with SessionLocal() as session:
            forms.complete_submission(
                session,
                submission=session.get(PortalFormSubmission, sid),
                contact=session.get(Contact, cid),
                responses_in={},
            )
            session.commit()

    def second():
        assert entered.wait(15)
        competing.set()
        if rollback:
            run()
        else:
            with pytest.raises(HTTPException) as err:
                run()
            assert err.value.status_code == 400

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(run), pool.submit(second)
        if rollback:
            with pytest.raises(RuntimeError):
                a.result(20)
        else:
            a.result(20)
        b.result(20)
    assert len(snapshots) == (2 if rollback else 1)
    assert (
        db.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.event_key == str(sid))
        )
        == 1
    )

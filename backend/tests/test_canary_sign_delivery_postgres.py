"""Synthetic contacts and fake mail only: no provider/network access."""

import json
import uuid
import smtplib
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Barrier
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from fastapi import HTTPException
from app.db import SessionLocal, begin_report_snapshot
from app import (
    canary_sign_delivery as mail,
    canary_sign_service as sign,
    notification_outbox as outbox,
)
from app.models import (
    CanarySignRequest,
    CanarySignRecipient,
    CanarySignStatus,
    CanarySignRecipientStatus,
    CanarySignOrderMode,
    CanarySignAuditEvent,
    Contact,
    CaseContact,
    ContactType,
    ContactPortalAccess,
    Case,
    FirmSettings,
    User,
    NotificationOutbox,
    NotificationAttempt,
)
from app.timeutil import utcnow
from tests.test_canary_sign_postgres import seed, submit


@pytest.fixture(autouse=True)
def isolated_postgres(db, monkeypatch):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("isolated PostgreSQL required")
    monkeypatch.setattr(mail, "resolve_alert_transport", lambda db: "smtp")


def fixture(count=1):
    rid, uid, cid, recipients, fields = seed(count)
    with SessionLocal() as db:
        db.get(Case, cid).portal_enabled = True
        settings = db.get(FirmSettings, 1)
        settings.client_portal_enabled = True
        settings.canary_sign_enabled = True
        for identity in recipients:
            r = db.get(CanarySignRecipient, identity)
            contact = Contact(
                id=uuid.uuid4(),
                type=ContactType.person,
                name="Synthetic recipient",
                email=r.email,
            )
            db.add(contact)
            db.flush()
            r.contact_id = contact.id
            cc = CaseContact(id=uuid.uuid4(),case_id=cid,contact_id=contact.id,type=ContactType.person,name=contact.name,email=contact.email)
            db.add(cc);db.flush();r.case_contact_id=cc.id
            from app.document_invitation_access import binding

            db.add(
                ContactPortalAccess(
                    id=uuid.uuid4(),
                    contact_id=contact.id,
                    code_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
                    enabled=True,
                    created_by_user_id=uid,
                    session_version=1,
                )
            )
        db.commit()
        from app.document_invitation_access import binding
        for identity in recipients:
            r=db.get(CanarySignRecipient,identity)
            r.document_invitation_binding=json.dumps(binding(db,cid,r.contact_id,r.case_contact_id),sort_keys=True)
        db.commit()
    return rid, uid, cid, recipients, fields


def queue(rid, kind="canary_sign_requested", key=None):
    from app.alert_dispatch import AlertKind

    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        sign._notify_recipients(
            db,
            req,
            sign._recipients_for_request(db, rid),
            kind=AlertKind(kind),
            event_key=key or str(rid),
        )
        db.commit()
        return list(
            db.scalars(
                select(NotificationOutbox.id).where(
                    NotificationOutbox.signing_request_id == rid,
                    NotificationOutbox.kind == kind,
                )
            )
        )


def test_atomic_enqueue_encrypts_links_and_dispatch_is_replay_safe():
    rid, uid, _, recips, _ = fixture()
    ids = queue(rid)
    assert queue(rid) == ids
    calls = []

    def fake(db, msg):
        calls.append(msg.notification_id)
        return "smtp"

    with SessionLocal() as db:
        row = db.get(NotificationOutbox, ids[0])
        token = db.get(CanarySignRecipient, recips[0]).sign_token
        assert token not in row.payload_enc and token not in row.binding_enc
        assert token not in json.dumps(mail.diagnostics(db))
    assert mail.deliver(ids[0], actor_id=uid, sender=fake)["state"] == "sent"
    assert mail.deliver(ids[0], actor_id=uid, sender=fake)["state"] == "sent"
    assert calls == [str(ids[0])]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(NotificationAttempt)
                .where(NotificationAttempt.notification_id == ids[0])
            )
            == 1
        )


def test_enqueue_rollback_has_no_delivery():
    rid, _, _, _, _ = fixture()
    from app.alert_dispatch import AlertKind

    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        sign._notify_recipients(
            db,
            req,
            sign._recipients_for_request(db, rid),
            kind=AlertKind.canary_sign_requested,
        )
        db.rollback()
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(NotificationOutbox.id).where(
                    NotificationOutbox.signing_request_id == rid
                )
            )
            is None
        )


@pytest.mark.parametrize("failure", ["timeout", "rejected"])
def test_failed_and_uncertain_delivery_require_review(failure):
    rid, uid, _, _, _ = fixture()
    identity = queue(rid)[0]
    calls = []

    def fake(db, msg):
        calls.append(1)
        if failure == "timeout":
            raise TimeoutError("Fake lost provider acknowledgement")
        raise smtplib.SMTPRecipientsRefused(
            {"synthetic@example.com": (550, b"rejected")}
        )

    result = mail.deliver(identity, actor_id=uid, sender=fake)
    assert result["state"] == ("uncertain" if failure == "timeout" else "failed")
    assert mail.deliver(identity, actor_id=uid, sender=fake)["state"] == result["state"]
    assert len(calls) == 1
    with SessionLocal() as db:
        if failure == "timeout":
            with pytest.raises(HTTPException):
                outbox.review(
                    db,
                    identity,
                    actor_id=uid,
                    expected_version=result["version"],
                    action="retry",
                    reason="Reviewed fake provider",
                )
            db.rollback()
        outbox.review(
            db,
            identity,
            actor_id=uid,
            expected_version=result["version"],
            action="retry",
            reason="Reviewed fake provider",
            acknowledge_uncertain=True,
        )
        db.commit()
    assert (
        mail.deliver(identity, actor_id=uid, sender=lambda *a: "smtp")["state"]
        == "sent"
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ("void", "request_inactive"),
        ("expire", "request_expired"),
        ("signed", "recipient_inactive"),
        ("email", "recipient_changed"),
        ("token", "recipient_changed"),
        ("disable", "document_access_changed"),
        ("rotate", "document_access_changed"),
        ("matter", "portal_disabled"),
    ],
)
def test_no_provider_call_after_eligibility_changes(change, code):
    rid, uid, cid, recips, _ = fixture()
    identity = queue(rid)[0]
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        r = db.get(CanarySignRecipient, recips[0])
        access = db.scalar(
            select(ContactPortalAccess).where(
                ContactPortalAccess.contact_id == r.contact_id
            )
        )
        if change == "void":
            req.status = CanarySignStatus.voided
        if change == "expire":
            req.expires_at = utcnow() - timedelta(days=1)
        if change == "signed":
            r.status = CanarySignRecipientStatus.signed
        if change == "email":
            r.email = "changed@example.com"
        if change == "token":
            r.sign_token = "changed"
        if change == "disable":
            access.enabled = False
        if change == "rotate":
            access.session_version += 1
        if change == "matter":
            db.get(Case, cid).portal_enabled = False
        db.commit()

    def forbidden(*args):
        pytest.fail("Provider must not be called")

    result = mail.deliver(identity, actor_id=uid, sender=forbidden)
    assert result["state"] == "cancelled" and result["last_code"] == code


def test_parallel_delivery_claims_once():
    rid, uid, _, _, _ = fixture()
    identity = queue(rid)[0]
    entered, observed = Event(), Event()
    calls = []

    def fake(db, msg):
        calls.append(1)
        entered.set()
        assert observed.wait(15)
        return "smtp"

    def contender():
        assert entered.wait(15)
        try:
            assert (
                mail.deliver(identity, actor_id=uid, sender=fake)["state"] == "sending"
            )
        finally:
            observed.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(mail.deliver, identity, actor_id=uid, sender=fake)
        b = pool.submit(contender)
        assert a.result(20)["state"] == "sent"
        b.result(20)
    assert calls == [1]


def test_sequential_invitation_waits_then_becomes_eligible():
    rid, uid, _, recips, fields = fixture(2)
    with SessionLocal() as db:
        db.get(CanarySignRequest, rid).order_mode = CanarySignOrderMode.sequential
        db.commit()
    queue(rid)
    with SessionLocal() as db:
        identity = db.scalar(
            select(NotificationOutbox.id).where(
                NotificationOutbox.signing_recipient_id == recips[1]
            )
        )

    def forbidden(*a):
        pytest.fail("Later signer must wait")

    assert (
        mail.deliver(identity, actor_id=uid, sender=forbidden)["eligibility"]
        == "waiting_turn"
    )
    assert submit(rid, recips[0], fields[0]) == "pending"
    assert (
        mail.deliver(identity, actor_id=uid, sender=lambda *a: "smtp")["state"]
        == "sent"
    )


def test_reminder_request_retry_is_idempotent():
    rid, uid, _, _, _ = fixture()
    key = uuid.uuid4()

    def remind():
        with SessionLocal() as db:
            sign.remind_signing_request(
                db,
                req=db.get(CanarySignRequest, rid),
                actor=db.get(User, uid),
                operation_key=key,
            )

    remind()
    remind()
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.signing_request_id == rid)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(CanarySignAuditEvent)
                .where(
                    CanarySignAuditEvent.signing_request_id == rid,
                    CanarySignAuditEvent.event_type == "reminded",
                )
            )
            == 1
        )
    remind()  # Replaying an acknowledged operation never creates another reminder.


def test_initial_send_retry_and_queue_failure_are_atomic(monkeypatch):
    rid, uid, cid, recips, _ = fixture()
    with SessionLocal() as db:
        old = db.get(CanarySignRequest, rid)
        old.status = CanarySignStatus.voided
        source = old.source_file_id
        contact = db.get(CanarySignRecipient, recips[0]).contact_id
        db.commit()
    key = uuid.uuid4()

    def send():
        with SessionLocal() as db:
            return sign.send_signing_request(
                db,
                case_id=cid,
                actor=db.get(User, uid),
                source_file_id=source,
                subject="Synthetic delivery",
                recipient_specs=[
                    {
                        "name": "Synthetic signer",
                        "email": "signer0@example.com",
                        "contact_id": contact,
                    }
                ],
                fields_specs=[
                    {
                        "field_type": "signature",
                        "page": 1,
                        "x_pct": 10,
                        "y_pct": 10,
                        "w_pct": 30,
                        "h_pct": 10,
                    }
                ],
                operation_key=key,
            ).id

    original = mail.enqueue

    def fail(*a, **k):
        raise RuntimeError("Fake queue failure")

    monkeypatch.setattr(mail, "enqueue", fail)
    with pytest.raises(RuntimeError):
        send()
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CanarySignRequest)
                .where(CanarySignRequest.case_id == cid)
            )
            == 1
        )
    monkeypatch.setattr(mail, "enqueue", original)
    first = send()
    assert send() == first
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.signing_request_id == first)
            )
            == 1
        )


def test_post_provider_commit_failure_never_reports_sent(monkeypatch):
    from sqlalchemy.orm import Session

    rid, uid, _, _, _ = fixture()
    identity = queue(rid)[0]
    original = Session.commit
    calls = []

    def commit(db):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Fake result persistence failure")
        original(db)

    monkeypatch.setattr(Session, "commit", commit)
    with pytest.raises(RuntimeError):
        mail.deliver(identity, actor_id=uid, sender=lambda *a: "smtp")
    monkeypatch.setattr(Session, "commit", original)
    with SessionLocal() as db:
        assert db.get(NotificationOutbox, identity).state == "sending"
    assert (
        mail.deliver(
            identity, actor_id=uid, sender=lambda *a: pytest.fail("No automatic replay")
        )["state"]
        == "sending"
    )


def test_claim_gap_rechecks_cancellation(monkeypatch):
    rid, uid, _, _, _ = fixture()
    identity = queue(rid)[0]
    original = mail._request_lock
    calls = []

    def lock(db, request_id):
        calls.append(1)
        if len(calls) == 2:
            with SessionLocal() as other:
                sign.void_signing_request(
                    other,
                    req=other.get(CanarySignRequest, rid),
                    actor=other.get(User, uid),
                    reason="Cancelled before provider call",
                )
        return original(db, request_id)

    monkeypatch.setattr(mail, "_request_lock", lock)
    result = mail.deliver(
        identity, actor_id=uid, sender=lambda *a: pytest.fail("Cancelled request")
    )
    assert result["state"] == "cancelled"


def test_staff_dispatch_cannot_send_external_signing_mail():
    rid, uid, _, _, _ = fixture()
    identity = queue(rid)[0]
    with pytest.raises(HTTPException):
        outbox.deliver(
            identity, actor_id=uid, sender=lambda *a: pytest.fail("Wrong dispatcher")
        )


def test_http_send_commits_before_fake_provider_and_replays(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.deps import get_current_user

    rid, uid, cid, recips, _ = fixture()
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, rid)
        req.status = CanarySignStatus.voided
        source = str(req.source_file_id)
        contact = str(db.get(CanarySignRecipient, recips[0]).contact_id)
        db.commit()

    def user():
        with SessionLocal() as db:
            yield db.get(User, uid)

    calls = []

    def fake(session, message):
        with SessionLocal() as db:
            row = db.get(NotificationOutbox, uuid.UUID(message.notification_id))
            assert row.state == "sending"
            assert (
                db.get(CanarySignRequest, row.signing_request_id).status
                == CanarySignStatus.pending
            )
        calls.append(message.notification_id)
        return "smtp"

    monkeypatch.setattr(mail, "send_firm_email", fake)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = user
    payload = {
        "source_file_id": source,
        "subject": "Synthetic HTTP signing",
        "recipients": [
            {
                "name": "Synthetic",
                "email": "signer0@example.com",
                "contact_id": contact,
                "routing_order": 1,
            }
        ],
        "fields": [
            {
                "field_type": "signature",
                "routing_order": 1,
                "required": True,
                "page": 1,
                "x_pct": 10,
                "y_pct": 10,
                "w_pct": 30,
                "h_pct": 10,
            }
        ],
    }
    headers = {"X-Document-Operation-ID": str(uuid.uuid4())}
    try:
        with TestClient(app) as client:
            first = client.post(
                f"/cases/{cid}/canary-sign/send", json=payload, headers=headers
            )
            assert first.status_code == 201, first.text
            second = client.post(
                f"/cases/{cid}/canary-sign/send", json=payload, headers=headers
            )
            assert (
                second.status_code == 201 and second.json()["id"] == first.json()["id"]
            )
            assert len(calls) == 1
            reminder_headers = {"X-Document-Operation-ID": str(uuid.uuid4())}
            reminder_path = (
                f"/cases/{cid}/canary-sign/requests/{first.json()['id']}/remind"
            )
            assert (
                client.post(
                    reminder_path, json={}, headers=reminder_headers
                ).status_code
                == 204
            )
            assert (
                client.post(
                    reminder_path, json={}, headers=reminder_headers
                ).status_code
                == 204
            )
            assert len(calls) == 2
            changed = client.post(
                f"/cases/{cid}/canary-sign/send",
                json={**payload, "subject": "Changed"},
                headers=headers,
            )
            assert changed.status_code == 409
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_transport_disabled_retains_reviewable_delivery(monkeypatch):
    rid, uid, _, _, _ = fixture()
    identity = queue(rid)[0]
    monkeypatch.setattr(mail, "resolve_alert_transport", lambda db: None)
    result = mail.deliver(
        identity, actor_id=uid, sender=lambda *a: pytest.fail("Disabled provider")
    )
    assert (
        result["state"] == "failed"
        and result["last_code"] == "transport_disabled_or_unconfigured"
    )


def test_concurrent_reminder_retries_do_not_duplicate_queue():
    rid, uid, _, _, _ = fixture()
    key = uuid.uuid4()
    barrier = Barrier(2)

    def run():
        with SessionLocal() as db:
            req = db.get(CanarySignRequest, rid)
            actor = db.get(User, uid)
            barrier.wait(10)
            sign.remind_signing_request(db, req=req, actor=actor, operation_key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fs = [pool.submit(run) for _ in range(2)]
        for f in fs:
            f.result(20)
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.signing_request_id == rid)
            )
            == 1
        )


def test_revoked_operator_in_claim_gap_does_not_call_provider(monkeypatch):
    rid, uid, _, _, _ = fixture()
    identity = queue(rid)[0]
    original = mail._actor
    calls = []

    def actor(db, actor_id, case_id):
        calls.append(1)
        if len(calls) == 2:
            raise HTTPException(403, "Synthetic access revocation")
        return original(db, actor_id, case_id)

    monkeypatch.setattr(mail, "_actor", actor)
    result = mail.deliver(
        identity, actor_id=uid, sender=lambda *a: pytest.fail("Revoked operator")
    )
    assert result["state"] == "cancelled"
    assert result["last_code"] == "operator_access_revoked"


def test_diagnostics_bound_details_and_report_totals():
    rid, _, _, _, _ = fixture(2)
    queue(rid)
    with SessionLocal() as db:
        begin_report_snapshot(db)
        result = mail.diagnostics(db, request_id=rid, limit=1)
        assert result["total"] == 2 and result["has_more"]
        assert len(result["deliveries"]) == 1 and result["states"] == {"pending": 2}
        with pytest.raises(ValueError):
            mail.diagnostics(db, limit=0)

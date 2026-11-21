"""Outbox failures never send uncommitted work or blindly repeat ambiguous delivery."""

import json
import smtplib
import uuid
from datetime import timedelta
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker
from app import notification_outbox as outbox
from app.models import (
    NotificationOutbox,
    NotificationAttempt,
    AuditEvent,
    User,
    UserRole,
    CaseLockMode,
)
from app.timeutil import utcnow
from tests.ledger_test_helpers import ledger_test_session, add_user, add_case


def fixture(db=None):
    db = db or ledger_test_session()
    admin = add_user(db)
    recipient = add_user(db, role=UserRole.user)
    case = add_case(db, fee_earner_user_id=recipient.id)
    db.commit()
    return db, admin, recipient, case


def enqueue(db, admin, recipient, case, key="invoice-test"):
    return outbox.enqueue_staff(
        db,
        kind="invoice_approved",
        event_key=key,
        case_id=case.id,
        recipient_user_id=recipient.id,
        actor_id=admin.id,
        context={
            "staff_name": "Recipient",
            "invoice_number": "TEST-42",
            "matter_label": "Private matter",
        },
    )


def setup_delivery(monkeypatch):
    db, admin, recipient, case = fixture()
    row = enqueue(db, admin, recipient, case)
    db.commit()
    identity, actor = row.id, admin.id
    factory = sessionmaker(bind=db.bind)
    monkeypatch.setattr(outbox, "resolve_alert_transport", lambda db: "smtp")
    return db, admin, recipient, case, identity, actor, factory


def test_enqueue_is_atomic_encrypted_and_deduplicated():
    db, admin, recipient, case = fixture()
    row = enqueue(db, admin, recipient, case)
    assert (
        "Private matter" not in row.payload_enc
        and recipient.email not in row.payload_enc
    )
    assert enqueue(db, admin, recipient, case).id == row.id
    db.rollback()
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
    row = enqueue(db, admin, recipient, case)
    db.commit()
    assert enqueue(db, admin, recipient, case).id == row.id
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "notification.queued")
        )
        == 1
    )
    db.close()


def test_provider_acceptance_is_recorded_and_repeated_dispatch_does_not_send(
    monkeypatch,
):
    db, _, _, _, identity, actor, factory = setup_delivery(monkeypatch)
    sender = Mock(return_value="smtp")
    assert (
        outbox.deliver(
            identity, actor_id=actor, session_factory=factory, sender=sender
        )["state"]
        == "sent"
    )
    assert (
        outbox.deliver(
            identity, actor_id=actor, session_factory=factory, sender=sender
        )["state"]
        == "sent"
    )
    assert sender.call_count == 1 and sender.call_args.args[1].notification_id == str(
        identity
    )
    db.expire_all()
    assert db.scalar(select(NotificationAttempt)).state == "sent"
    db.close()


@pytest.mark.parametrize(
    "error,expected",
    [
        (TimeoutError("private provider response"), "uncertain"),
        (
            smtplib.SMTPRecipientsRefused({"secret@example.com": (550, b"rejected")}),
            "failed",
        ),
    ],
)
def test_failed_and_uncertain_attempts_require_audited_review(
    monkeypatch, error, expected
):
    db, _, _, _, identity, actor, factory = setup_delivery(monkeypatch)
    sender = Mock(side_effect=error)
    first = outbox.deliver(
        identity, actor_id=actor, session_factory=factory, sender=sender
    )
    assert first["state"] == expected
    outbox.deliver(identity, actor_id=actor, session_factory=factory, sender=sender)
    assert sender.call_count == 1
    if expected == "uncertain":
        with pytest.raises(HTTPException):
            outbox.review(
                db,
                identity,
                actor_id=actor,
                expected_version=first["version"],
                action="retry",
                reason="Reviewed provider logs",
            )
        db.rollback()
    retry = outbox.review(
        db,
        identity,
        actor_id=actor,
        expected_version=first["version"],
        action="retry",
        reason="Reviewed provider evidence",
        acknowledge_uncertain=True,
    )
    db.commit()
    assert retry["state"] == "pending"
    sender.side_effect = None
    sender.return_value = "smtp"
    assert (
        outbox.deliver(
            identity, actor_id=actor, session_factory=factory, sender=sender
        )["state"]
        == "sent"
    )
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(NotificationAttempt)) == 2
    events = list(
        db.scalars(select(AuditEvent).where(AuditEvent.action.like("notification.%")))
    )
    assert any(e.action == "notification.retry" for e in events)
    assert "private provider response" not in "".join(e.meta_json or "" for e in events)
    db.close()


@pytest.mark.parametrize(
    "failure", ["disabled", "inactive", "email_changed", "permission", "payload"]
)
def test_preflight_failure_never_contacts_provider(monkeypatch, failure):
    db, _, recipient, case, identity, actor, factory = setup_delivery(monkeypatch)
    if failure == "disabled":
        monkeypatch.setattr(outbox, "resolve_alert_transport", lambda db: None)
    elif failure == "inactive":
        recipient.is_active = False
    elif failure == "email_changed":
        recipient.email = "replacement@example.com"
    elif failure == "permission":
        case.fee_earner_user_id = actor
        case.lock_mode = CaseLockMode.allow_list
    else:
        db.get(NotificationOutbox, identity).payload_enc = "corrupt"
    db.commit()
    sender = Mock()
    assert (
        outbox.deliver(
            identity, actor_id=actor, session_factory=factory, sender=sender
        )["state"]
        == "failed"
    )
    sender.assert_not_called()
    db.close()


def test_attempt_audit_failure_prevents_send(monkeypatch):
    db, _, _, _, identity, actor, factory = setup_delivery(monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError("Audit unavailable")

    monkeypatch.setattr(outbox, "log_event", fail)
    sender = Mock()
    with pytest.raises(RuntimeError):
        outbox.deliver(identity, actor_id=actor, session_factory=factory, sender=sender)
    sender.assert_not_called()
    db.expire_all()
    assert db.get(NotificationOutbox, identity).state == "pending"
    assert db.scalar(select(func.count()).select_from(NotificationAttempt)) == 0
    db.close()


def test_crash_after_acceptance_requires_stale_review_not_blind_retry(monkeypatch):
    db, _, _, _, identity, actor, factory = setup_delivery(monkeypatch)

    def crash(db, message):
        raise SystemExit("Process terminated after provider may have accepted")

    with pytest.raises(SystemExit):
        outbox.deliver(identity, actor_id=actor, session_factory=factory, sender=crash)
    sender = Mock()
    state = outbox.deliver(
        identity, actor_id=actor, session_factory=factory, sender=sender
    )
    assert state["state"] == "sending"
    sender.assert_not_called()
    with pytest.raises(HTTPException):
        outbox.review(
            db,
            identity,
            actor_id=actor,
            expected_version=state["version"],
            action="mark-uncertain",
            reason="Review interrupted worker",
        )
    db.rollback()
    row = db.get(NotificationOutbox, identity)
    row.updated_at = utcnow() - timedelta(minutes=16)
    db.commit()
    assert (
        outbox.review(
            db,
            identity,
            actor_id=actor,
            expected_version=state["version"],
            action="mark-uncertain",
            reason="Worker stopped; provider outcome unknown",
        )["state"]
        == "uncertain"
    )
    db.commit()
    db.close()


def test_non_admin_and_stale_review_cannot_retry(monkeypatch):
    db, _, recipient, _, identity, actor, factory = setup_delivery(monkeypatch)
    with pytest.raises(HTTPException) as error:
        outbox.deliver(
            identity, actor_id=recipient.id, session_factory=factory, sender=Mock()
        )
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        outbox.review(
            db,
            identity,
            actor_id=actor,
            expected_version=99,
            action="cancel",
            reason="Stale review",
        )
    db.rollback()
    assert db.get(NotificationOutbox, identity).state == "pending"
    db.close()


def test_login_codes_cannot_be_queued_and_still_use_existing_dispatch(monkeypatch):
    from app import alert_dispatch

    db, admin, recipient, case = fixture()
    with pytest.raises(ValueError):
        outbox.enqueue_staff(
            db,
            kind="portal_login_otp",
            event_key="login",
            case_id=case.id,
            recipient_user_id=recipient.id,
            context={"otp_code": "123456"},
            actor_id=admin.id,
        )
    sender = Mock(return_value="smtp")
    monkeypatch.setattr(alert_dispatch, "try_send_firm_email", sender)
    assert alert_dispatch.dispatch_alert(
        db,
        alert_dispatch.AlertKind.portal_login_otp,
        to_email=recipient.email,
        context={"otp_code": "123456"},
        actor_user_id=admin.id,
    )
    assert sender.call_count == 1 and sender.call_args.args[1].notification_id is None
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
    db.close()


@pytest.mark.parametrize("failed_commit", [1, 2])
def test_database_commit_failure_never_confirms_or_repeats_send(
    monkeypatch, failed_commit
):
    from sqlalchemy.orm import Session

    db, _, _, _, identity, actor, _ = setup_delivery(monkeypatch)
    commits = []

    class FaultSession(Session):
        def commit(self):
            commits.append(1)
            if len(commits) == failed_commit:
                raise RuntimeError("Injected commit failure")
            return super().commit()

    factory = sessionmaker(bind=db.bind, class_=FaultSession)
    sender = Mock(return_value="smtp")
    with pytest.raises(RuntimeError):
        outbox.deliver(identity, actor_id=actor, session_factory=factory, sender=sender)
    db.expire_all()
    assert db.get(NotificationOutbox, identity).state == (
        "pending" if failed_commit == 1 else "sending"
    )
    assert sender.call_count == failed_commit - 1
    if failed_commit == 2:
        outbox.deliver(identity, actor_id=actor, session_factory=factory, sender=sender)
        assert sender.call_count == 1
    db.close()


def test_invoice_approval_and_notice_roll_back_together(monkeypatch):
    from app import invoice_service as invoices
    from tests.test_invoice_service import _invoice_payload
    from app.ledger_service import get_ledger

    db, admin, recipient, case = fixture()
    inv = invoices.create_case_invoice(
        case.id, _invoice_payload(credit_user_id=recipient.id), admin, db
    )
    from app.models import CaseInvoice

    inv = db.get(CaseInvoice, inv.id)
    inv.created_by_user_id = recipient.id
    db.commit()
    original = outbox.log_event

    def fail(*args, **kwargs):
        raise RuntimeError("Outbox audit failed")

    monkeypatch.setattr(outbox, "log_event", fail)
    with pytest.raises(RuntimeError, match="Outbox audit failed"):
        invoices.approve_case_invoice(case.id, inv.id, admin, db)
    db.rollback()
    assert inv.status == invoices.INV_PENDING
    assert get_ledger(case.id, db).office.balance_pence == 0
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
    monkeypatch.setattr(outbox, "log_event", original)
    invoices.approve_case_invoice(case.id, inv.id, admin, db)
    db.commit()
    assert inv.status == invoices.INV_APPROVED
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    invoices.approve_case_invoice(case.id, inv.id, admin, db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    db.close()


@pytest.mark.parametrize("transport", ["smtp", "graph"])
def test_correlation_is_only_added_for_outbox_messages(monkeypatch, transport):
    from types import SimpleNamespace
    from app import firm_email_service as mail

    db, _, recipient, _ = fixture()
    monkeypatch.setattr(mail, "resolve_alert_transport", lambda db: transport)
    monkeypatch.setattr(
        mail,
        "get_email_integration_settings",
        lambda db: SimpleNamespace(
            graph_send_mailbox="sender@example.com", graph_send_from_name="Staff"
        ),
    )
    sender = Mock()
    monkeypatch.setattr(
        mail,
        "send_smtp_message" if transport == "smtp" else "send_graph_mail_message",
        sender,
    )
    msg = mail.FirmEmailMessage(
        to_email=recipient.email, subject="Code", body_text="123456"
    )
    mail.send_firm_email(db, msg)
    assert (
        "notification_id" not in sender.call_args.kwargs
        and "timeout_seconds" not in sender.call_args.kwargs
    )
    from dataclasses import replace

    msg = replace(msg, notification_id=str(uuid.uuid4()))
    mail.send_firm_email(db, msg)
    assert sender.call_args.kwargs["notification_id"] == msg.notification_id
    db.close()


def test_late_provider_result_cannot_overwrite_operator_review(monkeypatch):
    db, _, _, _, identity, actor, factory = setup_delivery(monkeypatch)

    def sender(session, message):
        with factory() as review_db:
            row = review_db.get(NotificationOutbox, identity)
            row.updated_at = utcnow() - timedelta(minutes=16)
            review_db.commit()
            state = outbox.review(
                review_db,
                identity,
                actor_id=actor,
                expected_version=row.version,
                action="mark-uncertain",
                reason="Worker exceeded allowed investigation window",
            )
            review_db.commit()
            outbox.review(
                review_db,
                identity,
                actor_id=actor,
                expected_version=state["version"],
                action="cancel",
                reason="Do not resend",
            )
            review_db.commit()
        return "smtp"

    assert (
        outbox.deliver(
            identity, actor_id=actor, session_factory=factory, sender=sender
        )["state"]
        == "cancelled"
    )
    db.expire_all()
    event = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "notification.late_result")
    )
    assert json.loads(event.meta_json)["reported_outcome"] == "sent"
    assert db.scalar(select(NotificationAttempt)).state == "uncertain"
    db.close()


def test_smtp_transport_uses_stable_message_id_and_timeout(monkeypatch):
    from types import SimpleNamespace
    from app import smtp_send

    settings = SimpleNamespace(
        enabled=True,
        host="isolated.invalid",
        from_email="sender@example.com",
        from_name="Staff",
        port=25,
        use_tls=False,
        username=None,
        password_enc=None,
    )
    monkeypatch.setattr(
        smtp_send, "get_smtp_notification_settings", lambda db: settings
    )
    connection = Mock()
    smtp = Mock()
    connection.__enter__ = Mock(return_value=smtp)
    connection.__exit__ = Mock(return_value=False)
    constructor = Mock(return_value=connection)
    monkeypatch.setattr(smtp_send.smtplib, "SMTP", constructor)
    identity = str(uuid.uuid4())
    for _ in range(2):
        smtp_send.send_smtp_message(
            None,
            to_email="recipient@example.com",
            subject="Test",
            body="Synthetic",
            notification_id=identity,
            timeout_seconds=30,
        )
    assert constructor.call_args.kwargs["timeout"] == 30
    assert [
        call.args[0]["Message-ID"] for call in smtp.send_message.call_args_list
    ] == [f"<{identity}@notifications.canary.invalid>"] * 2


@pytest.mark.parametrize("status", [202, 302, 500])
def test_graph_outbox_requires_explicit_provider_acceptance(monkeypatch, status):
    from app import graph_send_mail as graph

    monkeypatch.setattr(graph, "app_access_token", lambda db: "synthetic-token")
    client = Mock()
    client.post.return_value = Mock(status_code=status, text="Synthetic response")
    context = Mock()
    context.__enter__ = Mock(return_value=client)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(graph.httpx, "Client", Mock(return_value=context))
    identity = str(uuid.uuid4())

    def send():
        graph.send_graph_mail_message(
            None,
            send_mailbox="sender@example.com",
            to_email="recipient@example.com",
            subject="Test",
            body_text="Synthetic",
            notification_id=identity,
        )

    if status == 202:
        send()
    else:
        with pytest.raises(RuntimeError):
            send()
    assert client.post.call_count == 1
    assert client.post.call_args.kwargs["json"]["message"][
        "internetMessageHeaders"
    ] == [{"name": "x-canary-notification-id", "value": identity}]


def test_signing_completion_queue_failure_rolls_back_artifacts(tmp_path, monkeypatch):
    from tests.test_canary_sign_service import _session, _user, _case, _request
    from app import canary_sign_service as signing
    from app.models import File, CaseNote, CanarySignStatus, FirmSettings

    db = _session()
    for model in (
        File,
        CaseNote,
        FirmSettings,
        NotificationOutbox,
        NotificationAttempt,
    ):
        model.__table__.create(db.bind)
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case)
    monkeypatch.setattr(signing, "FILES_ROOT", tmp_path)
    source = signing._save_case_file(
        db,
        case_id=case.id,
        owner_id=user.id,
        folder_path="",
        filename="Original.pdf",
        mime_type="application/pdf",
        raw=b"original",
    )
    req.source_file_id = source.id
    req.snapshot_pdf_file_id = source.id
    req.sent_by_user_id = user.id
    db.commit()
    monkeypatch.setattr(signing, "stamp_signed_pdf", lambda *a: b"signed")
    monkeypatch.setattr(
        signing, "build_audit_certificate_pdf", lambda **kw: b"certificate"
    )
    monkeypatch.setattr(signing, "log_portal_activity", lambda *a, **kw: None)
    monkeypatch.setattr(signing, "list_portal_staff_recipient_users", lambda *a: [user])
    original = outbox.log_event

    def fail(*a, **kw):
        raise RuntimeError("Queue audit unavailable")

    monkeypatch.setattr(outbox, "log_event", fail)
    with pytest.raises(RuntimeError, match="Queue audit unavailable"):
        signing.complete_signing_request(db, req)
    db.rollback()
    assert req.status == CanarySignStatus.pending and req.signed_file_id is None
    assert db.scalar(select(func.count()).select_from(File)) == 1
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
    monkeypatch.setattr(outbox, "log_event", original)
    signing.complete_signing_request(db, req)
    signing.complete_signing_request(db, req)
    assert db.scalar(select(func.count()).select_from(File)) == 3
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    assert db.scalar(select(NotificationOutbox)).state == "pending"
    db.close()

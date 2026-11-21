"""Staff hooks queue atomically without changing external delivery."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from sqlalchemy import select, func
from app import notification_outbox as outbox
from app.models import (
    NotificationOutbox,
    NotificationAttempt,
    AuditEvent,
    FirmSettings,
    CasePortalStaffRecipient,
)
from app.timeutil import utcnow
from tests.test_notification_outbox import fixture, enqueue, setup_delivery


def portal_fixture():
    from tests.test_portal_form_complete import _session, _seed_user_case_contact

    db = _session(
        *(
            m.__table__
            for m in (
                FirmSettings,
                CasePortalStaffRecipient,
                NotificationOutbox,
                NotificationAttempt,
            )
        )
    )
    user, case, contact = _seed_user_case_contact(db)
    return db, user, case, contact


def test_portal_upload_notice_retry_does_not_repeat_business_action(monkeypatch):
    from app import portal_notifications as portal

    db, user, case, contact = portal_fixture()
    monkeypatch.setattr(portal, "default_grant_label", lambda *a: "Documents")
    key = uuid.uuid4()

    def queue():
        return portal.notify_portal_staff_client_upload(
            db,
            case_id=case.id,
            contact=contact,
            grant=SimpleNamespace(),
            filename="Sensitive.pdf",
            file_id=key,
        )

    queue()
    db.rollback()
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
    queue()
    db.commit()
    queue()
    db.commit()
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    assert db.scalar(select(NotificationOutbox)).state == "pending"
    db.close()


def form_fixture(db, user, case, contact):
    from app.models import (
        PortalFormTemplate,
        PortalFormSubmission,
        PortalFormSubmissionStatus,
    )

    template = PortalFormTemplate(
        id=uuid.uuid4(),
        name="Private form",
        reference=str(uuid.uuid4()),
        owner_id=user.id,
    )
    db.add(template)
    db.flush()
    sub = PortalFormSubmission(
        id=uuid.uuid4(),
        case_id=case.id,
        template_id=template.id,
        contact_id=contact.id,
        sent_by_user_id=user.id,
        status=PortalFormSubmissionStatus.pending,
        responses={},
        sent_at=utcnow(),
    )
    db.add(sub)
    db.commit()
    return sub


def test_form_and_outbox_rollback_together_then_queue_once(monkeypatch):
    from app import portal_form_service as forms
    from app.models import PortalFormSubmissionStatus

    db, user, case, contact = portal_fixture()
    sub = form_fixture(db, user, case, contact)
    snapshots = []

    def snapshot(*a, **kw):
        identity = uuid.uuid4()
        snapshots.append(identity)
        return SimpleNamespace(id=identity)

    monkeypatch.setattr(forms, "_save_snapshot_on_matter", snapshot)
    original = outbox.log_event

    def fail(*a, **kw):
        raise RuntimeError("Queue audit unavailable")

    monkeypatch.setattr(outbox, "log_event", fail)
    with pytest.raises(RuntimeError):
        forms.complete_submission(db, submission=sub, contact=contact, responses_in={})
    db.rollback()
    assert (
        sub.status == PortalFormSubmissionStatus.pending
        and sub.snapshot_file_id is None
    )
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
    monkeypatch.setattr(outbox, "log_event", original)
    forms.complete_submission(db, submission=sub, contact=contact, responses_in={})
    db.commit()
    assert sub.status == PortalFormSubmissionStatus.completed
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        forms.complete_submission(db, submission=sub, contact=contact, responses_in={})
    assert len(snapshots) == 2
    db.close()


@pytest.mark.parametrize("accepted", [True, False])
def test_quote_response_notice_is_transactional(monkeypatch, accepted):
    from app import quote_portal_service as quotes
    from app.models import (
        File,
        FileCategory,
        QuotePortalDelivery,
        QuotePortalDeliveryStatus,
    )

    db, user, case, contact = portal_fixture()
    f = File(
        id=uuid.uuid4(),
        case_id=case.id,
        owner_id=user.id,
        category=FileCategory.case_document,
        storage_path="synthetic",
        original_filename="Quote.pdf",
        size_bytes=5,
        version=1,
        mime_type="application/pdf",
    )
    db.add(f)
    db.flush()
    delivery = QuotePortalDelivery(
        id=uuid.uuid4(),
        case_id=case.id,
        contact_id=contact.id,
        file_id=f.id,
        file_version_at_send=1,
        status=QuotePortalDeliveryStatus.pending,
        sent_by_user_id=user.id,
    )
    db.add(delivery)
    db.commit()
    original = outbox.log_event

    def fail(*a, **kw):
        raise RuntimeError("Queue audit unavailable")

    monkeypatch.setattr(outbox, "log_event", fail)
    with pytest.raises(RuntimeError):
        quotes.respond_to_quote_delivery(
            db,
            delivery=delivery,
            contact=contact,
            accepted=accepted,
            decline_reason="Synthetic reason",
        )
    db.rollback()
    assert delivery.status == QuotePortalDeliveryStatus.pending
    monkeypatch.setattr(outbox, "log_event", original)
    quotes.respond_to_quote_delivery(
        db,
        delivery=delivery,
        contact=contact,
        accepted=accepted,
        decline_reason="Synthetic reason",
    )
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    db.close()


def calendar_fixture():
    from app.models import (
        CalendarEventEmailAlertSubscription,
        CalendarEventNotificationSent,
        UserCalendar,
        UserCalendarShare,
        UserCalendarSubscription,
    )

    db, admin, user, case = fixture()
    for model in (
        CalendarEventEmailAlertSubscription,
        CalendarEventNotificationSent,
        UserCalendar,
        UserCalendarShare,
        UserCalendarSubscription,
    ):
        model.__table__.create(db.bind)
    cal = UserCalendar(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name="Private calendar",
        radicale_slug="synthetic",
    )
    db.add(cal)
    db.flush()
    sub = CalendarEventEmailAlertSubscription(
        id=uuid.uuid4(),
        user_id=user.id,
        event_key=f"r|{cal.id}|synthetic",
        enabled=True,
        anchor_date=utcnow().date(),
        title_snapshot="Private event",
        all_day=True,
    )
    db.add(sub)
    db.commit()
    return db, admin, user, sub, cal


@pytest.mark.parametrize("change", ["none", "disabled", "changed", "expired", "access"])
def test_calendar_queue_deduplicates_and_rechecks_subscription(monkeypatch, change):
    from app.calendar_email_alert_service import process_due_calendar_notifications
    from sqlalchemy.orm import sessionmaker

    db, admin, user, sub, cal = calendar_fixture()
    process_due_calendar_notifications(db)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 0
    process_due_calendar_notifications(db)
    db.commit()
    process_due_calendar_notifications(db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    row = db.scalar(select(NotificationOutbox))
    if change == "disabled":
        sub.enabled = False
    elif change == "changed":
        sub.title_snapshot = "Changed"
    elif change == "expired":
        row.event_key = row.event_key.replace(
            utcnow().date().isoformat(),
            (utcnow().date() - timedelta(days=1)).isoformat(),
        )
    elif change == "access":
        cal.owner_user_id = admin.id
    db.commit()
    sender = Mock(return_value="smtp")
    monkeypatch.setattr(outbox, "resolve_alert_transport", lambda db: "smtp")
    result = outbox.deliver(
        row.id,
        actor_id=admin.id,
        session_factory=sessionmaker(bind=db.bind),
        sender=sender,
    )
    assert result["state"] == ("sent" if change == "none" else "failed")
    assert sender.call_count == (1 if change == "none" else 0)
    db.close()


def test_diagnostics_are_aggregate_only_and_detect_stale_attempts(monkeypatch):
    from app.notification_diagnostics import diagnostics

    db, _, _, _, identity, actor, factory = setup_delivery(monkeypatch)

    def crash(*args):
        raise SystemExit()

    with pytest.raises(SystemExit):
        outbox.deliver(identity, actor_id=actor, session_factory=factory, sender=crash)
    db.expire_all()
    row = db.get(NotificationOutbox, identity)
    row.updated_at = utcnow() - timedelta(minutes=16)
    db.commit()
    result = diagnostics(db)
    assert (
        result["stale_sending"] == 1
        and result["attention_required"]
        and result["attempts"] == 1
    )
    assert str(identity) not in str(result) and "Private matter" not in str(result)
    assert db.get(NotificationOutbox, identity).state == "sending"
    db.close()


def test_portal_upload_queue_failure_does_not_commit_file(tmp_path, monkeypatch):
    from io import BytesIO
    from fastapi import UploadFile
    from app import portal_browse_service as browse, portal_notifications as portal
    from app.models import File

    db, user, case, contact = portal_fixture()
    grant = SimpleNamespace(id=uuid.uuid4(), case_id=case.id, folder_path="")
    monkeypatch.setattr("app.file_storage.FILES_ROOT", tmp_path)
    monkeypatch.setattr("app.deps.require_portal_not_preview", lambda *a: None)
    monkeypatch.setattr(browse, "get_grant_for_contact", lambda *a, **k: grant)
    monkeypatch.setattr("app.portal_policy.fresh", lambda *a, **k: grant)
    monkeypatch.setattr(browse, "ensure_upload_folder_allowed", lambda **k: "")
    monkeypatch.setattr(browse, "user_may_be_fee_earner", lambda *a: True)
    monkeypatch.setattr(browse, "log_portal_activity", lambda *a, **k: None)
    monkeypatch.setattr(portal, "default_grant_label", lambda *a: "Documents")
    original = outbox.log_event

    def fail(*a, **kw):
        raise RuntimeError("Queue unavailable")

    def upload():
        return browse.upload_file(
            grant.id,
            UploadFile(filename="Synthetic.txt", file=BytesIO(b"preserved bytes")),
            folder="",
            contact=contact,
            session=SimpleNamespace(audience="client"),
            db=db,
        )

    monkeypatch.setattr(outbox, "log_event", fail)
    with pytest.raises(RuntimeError):
        upload()
    db.rollback()
    assert db.scalar(select(func.count()).select_from(File)) == 0
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]
    monkeypatch.setattr(outbox, "log_event", original)
    result = upload()
    row = db.get(File, result.id)
    assert (tmp_path / row.storage_path).read_bytes() == b"preserved bytes"
    assert db.scalar(select(func.count()).select_from(NotificationOutbox)) == 1
    db.close()


def test_form_queue_failure_preserves_previous_snapshot_bytes(tmp_path, monkeypatch):
    from app import portal_form_service as forms
    from app.models import File, FileCategory

    db, user, case, contact = portal_fixture()
    sub = form_fixture(db, user, case, contact)
    old = tmp_path / "old.docx"
    old.write_bytes(b"pending form")
    row = File(
        id=uuid.uuid4(),
        case_id=case.id,
        owner_id=user.id,
        category=FileCategory.case_document,
        storage_path="old.docx",
        original_filename="Form.docx",
        size_bytes=12,
        version=1,
        mime_type="application/test",
    )
    db.add(row)
    db.flush()
    sub.snapshot_file_id = row.id
    db.commit()
    monkeypatch.setattr(forms, "FILES_ROOT", tmp_path)
    monkeypatch.setattr(forms, "_render_submission_docx", lambda **k: b"completed form")
    original = outbox.log_event

    def fail(*a, **kw):
        raise RuntimeError("Queue unavailable")

    monkeypatch.setattr(outbox, "log_event", fail)
    with pytest.raises(RuntimeError):
        forms.complete_submission(db, submission=sub, contact=contact, responses_in={})
    db.rollback()
    assert row.storage_path == "old.docx" and old.read_bytes() == b"pending form"
    monkeypatch.setattr(outbox, "log_event", original)
    forms.complete_submission(db, submission=sub, contact=contact, responses_in={})
    db.commit()
    assert (
        row.storage_path != "old.docx"
        and (tmp_path / row.storage_path).read_bytes() == b"completed form"
    )
    assert old.read_bytes() == b"pending form"
    db.close()

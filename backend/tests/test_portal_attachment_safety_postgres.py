"""Additional attachment consistency and revoked-delivery regressions."""

import uuid
from sqlalchemy import select
from app.db import SessionLocal
from app.models import (
    PortalFormSubmission,
    CanarySignRequest,
    CanarySignRecipient,
    CaseContact,
    User,
)
from tests.test_portal_access_postgres import safe, data, headers


def test_stale_submission_cannot_erase_uploaded_attachment(data):
    path = f"/portal/forms/{data['sub']}"
    upload = data["client"].post(
        path + "/upload",
        params={"field_key": "attachments"},
        headers=headers(data),
        files={"upload": ("keep.txt", b"keep bytes", "text/plain")},
    )
    assert upload.status_code == 200
    response = data["client"].post(
        path + "/submit", headers=headers(data), json={"responses": {"attachments": []}}
    )
    assert response.status_code == 409
    with SessionLocal() as db:
        row = db.get(PortalFormSubmission, data["sub"])
        assert row.status.value == "pending"
        assert row.responses["attachments"][0]["file_id"] == upload.json()["file_id"]
    assert (
        data["client"]
        .post(path + "/submit", headers=headers(data), json={"responses": {}})
        .status_code
        == 200
    )


def test_arbitrary_attachment_reference_is_rejected(data):
    response = data["client"].post(
        f"/portal/forms/{data['sub']}/submit",
        headers=headers(data),
        json={
            "responses": {
                "attachments": [
                    {"file_id": str(data["file"]), "filename": "forged.txt"}
                ]
            }
        },
    )
    assert response.status_code == 409


def test_last_contact_removal_cancels_queued_signing_invitation(data):
    from app import canary_sign_delivery as mail, canary_sign_service as sign
    from app.alert_dispatch import AlertKind
    from app.models import NotificationOutbox, ContactType
    from app.routers.case_contacts import remove_case_contact

    with SessionLocal() as db:
        req = db.get(CanarySignRequest, data["rid"])
        sign._notify_recipients(
            db,
            req,
            [db.get(CanarySignRecipient, data["recip"])],
            kind=AlertKind.canary_sign_requested,
            event_key=str(uuid.uuid4()),
        )
        cc = db.scalar(select(CaseContact).where(CaseContact.case_id == data["cid"], CaseContact.contact_id == data["contact"]))
        cc.matter_contact_type = "client"
        db.commit()
        delivery = db.scalar(
            select(NotificationOutbox.id).where(
                NotificationOutbox.signing_request_id == req.id
            )
        )
        remove_case_contact(
            case_id=data["cid"],
            case_contact_id=cc.id,
            user=db.get(User, data["uid"]),
            db=db,
        )
    calls = []
    result = mail.deliver(
        delivery, actor_id=data["uid"], sender=lambda *args: calls.append(args)
    )
    assert result["state"] == "cancelled"
    assert not calls


def test_upload_rechecks_session_expiry_after_streaming(data, monkeypatch):
    from app import portal_policy, portal_browse_service
    from tests.test_portal_access_postgres import url

    original = portal_browse_service.stream_upload_to_path

    def expire(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(portal_policy, "time", lambda: 9999999999)
        return result

    monkeypatch.setattr(portal_browse_service, "stream_upload_to_path", expire)
    response = data["client"].post(
        url(data, "files"),
        headers=headers(data),
        files={"upload": ("expired.txt", b"synthetic", "text/plain")},
    )
    assert response.status_code == 401

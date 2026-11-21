"""Portal authorization and concurrency regression tests.
All contacts/documents synthetic; internal Docker network; production code read-only.
"""

import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Barrier
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import (
    Case,
    Contact,
    ContactType,
    ContactPortalAccess,
    MatterPortalAccess,
    ContactPortalGrant,
    File,
    FirmSettings,
    CanarySignRequest,
    CanarySignRecipient,
    CanarySignStatus,
    PortalFormTemplate,
    PortalFormTemplateField,
    PortalFormFieldType,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
)
from app.security import create_portal_session_token
from app.portal_service import (
    store_portal_access_code,
    store_matter_portal_access_code,
    generate_access_code,
)
from app import (
    canary_sign_service as sign,
    portal_browse_service as browse,
    portal_form_service as forms,
)
from app.timeutil import utcnow
from tests.test_canary_sign_delivery_postgres import fixture as signing_fixture


@pytest.fixture(autouse=True)
def safe(db, monkeypatch):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("isolated PostgreSQL required")
    from app import canary_sign_delivery

    monkeypatch.setattr(canary_sign_delivery, "dispatch_request", lambda *a, **kw: None)
    with SessionLocal() as db:
        settings = db.get(FirmSettings, 1)
        settings.client_portal_enabled = True
        settings.canary_sign_enabled = True
        db.commit()
    yield
    with SessionLocal() as db:
        settings = db.get(FirmSettings, 1)
        settings.client_portal_enabled = True
        settings.canary_sign_enabled = True
        db.commit()


@pytest.fixture
def data():
    rid, uid, cid, recips, fields = signing_fixture()
    with SessionLocal() as db:
        recip = db.get(CanarySignRecipient, recips[0])
        contact = recip.contact_id
        access = db.scalar(
            select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact)
        )
        code = generate_access_code()
        store_portal_access_code(access, code)
        recip.portal_access_version = access.session_version
        other = Contact(
            id=uuid.uuid4(),
            type=ContactType.person,
            name="Other synthetic client",
            email="other@example.invalid",
        )
        db.add(other)
        db.flush()
        db.add(
            ContactPortalAccess(
                contact_id=other.id,
                code_sha256=uuid.uuid4().hex * 2,
                created_by_user_id=uid,
                enabled=True,
            )
        )
        from tests.ledger_test_helpers import add_case

        case2 = add_case(db, fee_earner_user_id=uid)
        case2.portal_enabled = True
        access2 = MatterPortalAccess(
            case_id=case2.id, contact_id=contact, created_by_user_id=uid, enabled=True
        )
        exchange_code = generate_access_code()
        store_matter_portal_access_code(access2, exchange_code)
        db.add(access2)
        file = sign._save_case_file(
            db,
            case_id=cid,
            owner_id=uid,
            folder_path="Shared",
            filename="private.txt",
            mime_type="text/plain",
            raw=b"synthetic confidential content",
        )
        grant = ContactPortalGrant(
            id=uuid.uuid4(),
            contact_id=contact,
            case_id=cid,
            folder_path="Shared",
            created_by_user_id=uid,
            can_download=True,
            can_upload=True,
        )
        db.add(grant)
        template = PortalFormTemplate(
            id=uuid.uuid4(),
            name="Confidential form",
            reference=uuid.uuid4().hex,
            owner_id=uid,
        )
        db.add(template)
        db.flush()
        db.add(
            PortalFormTemplateField(
                template_id=template.id,
                field_key="attachments",
                label="Attachments",
                field_type=PortalFormFieldType.files,
                required=False,
            )
        )
        sub = PortalFormSubmission(
            id=uuid.uuid4(),
            case_id=cid,
            template_id=template.id,
            contact_id=contact,
            sent_by_user_id=uid,
            responses={},
        )
        db.add(sub)
        db.commit()
        result = dict(
            rid=rid,
            uid=uid,
            cid=cid,
            contact=contact,
            other=other.id,
            access=access.id,
            exchange_access=access2.id,
            other_case=case2.id,
            file=file.id,
            grant=grant.id,
            sub=sub.id,
            recip=recips[0],
            field=fields[0],
            sign_token=recip.sign_token,
        )
    client = TestClient(
        app
    )  # no lifespan: no startup tasks; full production routes/middleware/dependencies
    auth = client.post("/portal/auth", json={"access_code": code})
    assert auth.status_code == 200, auth.text
    result["token"] = auth.json()["session_token"]
    auth = client.post("/portal/auth", json={"access_code": exchange_code})
    assert auth.status_code == 200, auth.text
    result["exchange_token"] = auth.json()["session_token"]
    result["other_token"] = create_portal_session_token(contact_id=str(result["other"]))
    result["client"] = client
    return result


def headers(d, key="token"):
    return {"Authorization": "Bearer " + d[key]}


def url(d, kind):
    return {
        "file": f"/portal/grants/{d['grant']}/files/{d['file']}",
        "files": f"/portal/grants/{d['grant']}/files",
        "zip": f"/portal/grants/{d['grant']}/files/download-zip",
        "browse": f"/portal/grants/{d['grant']}/browse",
        "form": f"/portal/forms/{d['sub']}",
        "pdf": f"/portal/canary-sign/{d['rid']}/pdf",
        "sign": f"/portal/canary-sign/{d['rid']}/sign",
    }[kind]


def get(d, kind, key="token"):
    return d["client"].get(url(d, kind), headers=headers(d, key))


def revoke(d, mode):
    with SessionLocal() as db:
        if mode == "disabled":
            db.get(ContactPortalAccess, d["access"]).enabled = False
        elif mode == "version":
            db.get(ContactPortalAccess, d["access"]).session_version += 1
        elif mode == "expired":
            db.get(ContactPortalAccess, d["access"]).expires_at = utcnow() - timedelta(
                seconds=1
            )
        elif mode == "matter":
            db.get(Case, d["cid"]).portal_enabled = False
        elif mode == "firm":
            db.get(FirmSettings, 1).client_portal_enabled = False
        elif mode == "grant":
            db.get(ContactPortalGrant, d["grant"]).expires_at = utcnow() - timedelta(
                seconds=1
            )
        db.commit()


@pytest.mark.parametrize("kind", ["file", "files", "zip", "browse", "form", "pdf"])
def test_other_client_cannot_read(data, kind):
    assert get(data, kind, "other_token").status_code in (401, 403, 404)


@pytest.mark.parametrize("mode", ["disabled", "version", "expired"])
@pytest.mark.parametrize("kind", ["file", "form", "pdf"])
def test_new_requests_reject_revoked_session(data, mode, kind):
    revoke(data, mode)
    assert get(data, kind).status_code == 401


@pytest.mark.parametrize("mode", ["matter", "firm", "grant"])
def test_folder_download_respects_disable(data, mode):
    revoke(data, mode)
    assert get(data, "file").status_code in (403, 404)


def test_exchange_browse_is_matter_scoped(data):
    assert get(data, "browse", "exchange_token").status_code == 404


@pytest.mark.parametrize("kind", ["file", "files", "zip", "form", "pdf"])
def test_exchange_cannot_read_another_matter(data, kind):
    response = get(data, kind, "exchange_token")
    assert response.status_code in (
        401,
        403,
        404,
    ), f"{kind}: HTTP {response.status_code}"


@pytest.mark.parametrize("mode", ["matter", "firm"])
@pytest.mark.parametrize("kind", ["form", "pdf"])
def test_disabled_portal_blocks_direct_workflows(data, mode, kind):
    revoke(data, mode)
    response = get(data, kind)
    assert response.status_code in (
        401,
        403,
        404,
    ), f"{mode}/{kind}: HTTP {response.status_code}"


def test_disabled_matter_cannot_sign(data):
    revoke(data, "matter")
    response = data["client"].post(
        url(data, "sign"),
        headers=headers(data),
        json={
            "field_values": {str(data["field"]): {"text": "Synthetic signature"}},
            "consent": True,
        },
    )
    assert response.status_code in (
        401,
        403,
        404,
    ), f"HTTP {response.status_code}: {response.text[:180]}"


@pytest.mark.parametrize("mode", ["disabled", "version", "expired"])
def test_open_link_rejected_after_session_revocation(data, mode):
    response = data["client"].post(
        url(data, "file") + "/open-token", headers=headers(data)
    )
    assert response.status_code == 200
    token = response.json()["token"]
    revoke(data, mode)
    response = data["client"].get(url(data, "file") + "/open", params={"token": token})
    assert response.status_code in (
        401,
        403,
        404,
    ), f"HTTP {response.status_code}: {response.content!r}"


@pytest.mark.parametrize("mode", ["matter", "firm", "grant"])
def test_open_link_respects_grant_and_portal_revocation(data, mode):
    token = (
        data["client"]
        .post(url(data, "file") + "/open-token", headers=headers(data))
        .json()["token"]
    )
    revoke(data, mode)
    assert data["client"].get(
        url(data, "file") + "/open", params={"token": token}
    ).status_code in (403, 404)


@pytest.mark.parametrize("state", ["pending", "expired", "voided", "completed"])
def test_old_sign_link_does_not_bypass_rotation(data, state):
    with SessionLocal() as db:
        access = db.get(ContactPortalAccess, data["access"])
        store_portal_access_code(access, generate_access_code())
        access.session_version += 1
        request = db.get(CanarySignRequest, data["rid"])
        if state == "expired":
            request.expires_at = utcnow() - timedelta(days=1)
        elif state != "pending":
            request.status = CanarySignStatus(state)
        db.commit()
    assert get(data, "file").status_code == 401
    exchange = data["client"].post(
        "/portal/canary-sign-exchange", json={"sign_token": data["sign_token"]}
    )
    if exchange.status_code == 200:
        new_token = exchange.json()["session_token"]
        response = data["client"].get(
            url(data, "file"), headers={"Authorization": "Bearer " + new_token}
        )
        assert response.status_code in (
            401,
            403,
            404,
        ), f"{state}: old link issued new session, file HTTP {response.status_code}"
    else:
        assert exchange.status_code in (401, 403, 404)


@pytest.mark.parametrize("mode", ["disabled", "version", "matter", "grant"])
def test_upload_racing_revocation(data, monkeypatch, mode):
    entered = Event()
    resume = Event()
    original = browse.stream_upload_to_path

    def pause(*a, **kw):
        entered.set()
        assert resume.wait(15)
        return original(*a, **kw)

    monkeypatch.setattr(browse, "stream_upload_to_path", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            data["client"].post,
            url(data, "files"),
            headers=headers(data),
            files={"upload": ("race.txt", b"race synthetic bytes", "text/plain")},
        )
        try:
            assert entered.wait(15)
            revoke(data, mode)
        finally:
            resume.set()
        response = future.result(20)
    assert response.status_code in (
        401,
        403,
        404,
        409,
    ), f"{mode}: upload HTTP {response.status_code}"


def test_two_concurrent_form_uploads_preserve_both(data, monkeypatch):
    barrier = Barrier(2)
    original = forms.write_bytes_atomic

    def pause(*a, **kw):
        barrier.wait(timeout=15)
        return original(*a, **kw)

    monkeypatch.setattr(forms, "write_bytes_atomic", pause)

    def upload(i):
        return data["client"].post(
            f"/portal/forms/{data['sub']}/upload",
            params={"field_key": "attachments"},
            headers=headers(data),
            files={"upload": (f"{i}.txt", b"synthetic bytes", "text/plain")},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(upload, [1, 2]))
    assert [r.status_code for r in responses] == [200, 200]
    with SessionLocal() as db:
        saved = db.get(PortalFormSubmission, data["sub"]).responses["attachments"]
        ids = {r.json()["file_id"] for r in responses}
        assert {
            v["file_id"] for v in saved
        } == ids, f"two HTTP200 uploads but {len(saved)} linked response"


def test_sign_racing_revocation(data, monkeypatch):
    from app.routers import portal

    entered = Event()
    resume = Event()
    original = portal.canary_submit_signature

    def pause(*a, **kw):
        entered.set()
        assert resume.wait(15)
        return original(*a, **kw)

    monkeypatch.setattr(portal, "canary_submit_signature", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            data["client"].post,
            url(data, "sign"),
            headers=headers(data),
            json={
                "field_values": {str(data["field"]): {"text": "Synthetic signature"}},
                "consent": True,
            },
        )
        try:
            assert entered.wait(15)
            revoke(data, "disabled")
        finally:
            resume.set()
        response = future.result(20)
    with SessionLocal() as db:
        persisted = db.get(CanarySignRequest, data["rid"]).status.value
    assert response.status_code in (
        401,
        403,
        404,
        409,
    ), f"HTTP {response.status_code}; persisted status {persisted}"


def test_form_upload_racing_completion(data, monkeypatch):
    entered = Event()
    resume = Event()
    original = forms.write_bytes_atomic

    def pause(*a, **kw):
        entered.set()
        assert resume.wait(15)
        return original(*a, **kw)

    monkeypatch.setattr(forms, "write_bytes_atomic", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            data["client"].post,
            f"/portal/forms/{data['sub']}/upload",
            params={"field_key": "attachments"},
            headers=headers(data),
            files={"upload": ("late.txt", b"synthetic bytes", "text/plain")},
        )
        try:
            assert entered.wait(15)
            result = data["client"].post(
                f"/portal/forms/{data['sub']}/submit",
                headers=headers(data),
                json={"responses": {}},
            )
            assert result.status_code == 200, result.text
        finally:
            resume.set()
        response = future.result(20)
    with SessionLocal() as db:
        sub = db.get(PortalFormSubmission, data["sub"])
        assert sub.status == PortalFormSubmissionStatus.completed
        assert response.status_code in (
            400,
            401,
            403,
            404,
            409,
        ), f'late upload HTTP {response.status_code}; completed form now has {len(sub.responses.get("attachments",[]))} attachments'


def test_remove_contact_revokes_matter_content(data):
    from app.models import CaseContact, User
    from app.routers.case_contacts import remove_case_contact

    with SessionLocal() as db:
        cc = CaseContact(
            case_id=data["cid"],
            contact_id=data["contact"],
            type=ContactType.person,
            name="Synthetic client",
            matter_contact_type="client",
        )
        db.add(cc)
        db.commit()
        identity = cc.id
        remove_case_contact(
            case_id=data["cid"],
            case_contact_id=identity,
            user=db.get(User, data["uid"]),
            db=db,
        )
    response = get(data, "file")
    assert response.status_code in (
        401,
        403,
        404,
    ), f"HTTP {response.status_code} after staff removal"


@pytest.mark.parametrize("kind", ["file", "form", "pdf"])
def test_missing_session_is_rejected(data, kind):
    assert data["client"].get(url(data, kind)).status_code == 401


def test_open_token_bound_to_file(data):
    token = (
        data["client"]
        .post(url(data, "file") + "/open-token", headers=headers(data))
        .json()["token"]
    )
    response = data["client"].get(
        f"/portal/grants/{data['grant']}/files/{uuid.uuid4()}/open",
        params={"token": token},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("audience", ["exchange", "preview"])
def test_nonclient_sessions_cannot_sign_or_submit_forms(data, audience):
    if audience == "exchange":
        token = data["exchange_token"]
    else:
        from app.security import decode_portal_session_token

        version = decode_portal_session_token(data["token"]).session_version
        token = create_portal_session_token(
            contact_id=str(data["contact"]), staff_preview=True, session_version=version
        )
    h = {"Authorization": "Bearer " + token}
    assert (
        data["client"]
        .post(url(data, "sign"), headers=h, json={"field_values": {}, "consent": True})
        .status_code
        == 403
    )
    assert (
        data["client"]
        .post(f"/portal/forms/{data['sub']}/submit", headers=h, json={"responses": {}})
        .status_code
        == 403
    )


def test_fresh_signing_link_is_scoped_and_can_complete(data):
    exchange = data["client"].post(
        "/portal/canary-sign-exchange", json={"sign_token": data["sign_token"]}
    )
    assert exchange.status_code == 200, exchange.text
    h = {"Authorization": "Bearer " + exchange.json()["session_token"]}
    assert exchange.json()["grants"] == []
    assert data["client"].get("/portal/session", headers=h).json()["grants"] == []
    assert data["client"].get(url(data, "file"), headers=h).status_code == 403
    assert data["client"].get(url(data, "form"), headers=h).status_code == 403
    assert data["client"].get("/portal/forms", headers=h).json() == []
    assert data["client"].get("/portal/quote-deliveries", headers=h).json() == []
    assert data["client"].get(url(data, "pdf"), headers=h).status_code == 200
    actions = data["client"].get("/portal/client-actions", headers=h)
    assert actions.status_code == 200, actions.text
    assert all(
        x["kind"] == "canary_sign" and x["id"] == str(data["rid"])
        for items in actions.json().values()
        for x in items
    )
    response = data["client"].post(
        url(data, "sign"),
        headers=h,
        json={
            "field_values": {str(data["field"]): {"text": "Synthetic signature"}},
            "consent": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert (
        data["client"]
        .get(f"/portal/canary-sign/{data['rid']}/signed-pdf", headers=h)
        .status_code
        == 200
    )
    assert (
        data["client"]
        .post("/portal/canary-sign-exchange", json={"sign_token": data["sign_token"]})
        .status_code
        == 401
    )


def test_existing_signing_session_dies_on_rotation(data):
    exchange = data["client"].post(
        "/portal/canary-sign-exchange", json={"sign_token": data["sign_token"]}
    )
    assert exchange.status_code == 200
    revoke(data, "version")
    assert (
        data["client"]
        .get(
            url(data, "pdf"),
            headers={"Authorization": "Bearer " + exchange.json()["session_token"]},
        )
        .status_code
        == 401
    )


def test_unbound_legacy_signing_link_requires_login(data):
    with SessionLocal() as db:
        db.get(CanarySignRecipient, data["recip"]).portal_access_version = None
        db.commit()
    assert (
        data["client"]
        .post("/portal/canary-sign-exchange", json={"sign_token": data["sign_token"]})
        .status_code
        == 401
    )
    assert get(data, "pdf").status_code == 200


def test_form_upload_rejected_on_concurrent_revocation(data, monkeypatch):
    from app.file_storage import FILES_ROOT

    before = set(FILES_ROOT.rglob("*"))
    entered = Event()
    resume = Event()
    original = forms.write_bytes_atomic

    def pause(*a, **kw):
        entered.set()
        assert resume.wait(15)
        return original(*a, **kw)

    monkeypatch.setattr(forms, "write_bytes_atomic", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            data["client"].post,
            f"/portal/forms/{data['sub']}/upload",
            params={"field_key": "attachments"},
            headers=headers(data),
            files={"upload": ("revoked.txt", b"synthetic bytes", "text/plain")},
        )
        try:
            assert entered.wait(15)
            revoke(data, "disabled")
        finally:
            resume.set()
        response = future.result(20)
    assert response.status_code == 401
    with SessionLocal() as db:
        assert db.get(PortalFormSubmission, data["sub"]).responses == {}
    assert not [p for p in set(FILES_ROOT.rglob("*")) - before if p.is_file()]


def test_revocation_waits_for_authorized_upload_commit(data, monkeypatch):
    entered = Event()
    resume = Event()
    revoking = Event()
    original = browse.notify_portal_staff_client_upload

    def pause(*a, **kw):
        entered.set()
        assert resume.wait(15)
        return original(*a, **kw)

    monkeypatch.setattr(browse, "notify_portal_staff_client_upload", pause)

    def disable():
        revoking.set()
        revoke(data, "disabled")

    with ThreadPoolExecutor(max_workers=2) as pool:
        upload = pool.submit(
            data["client"].post,
            url(data, "files"),
            headers=headers(data),
            files={"upload": ("before-revoke.txt", b"synthetic bytes", "text/plain")},
        )
        assert entered.wait(15)
        revocation = pool.submit(disable)
        try:
            assert revoking.wait(15)
            from concurrent.futures import TimeoutError

            with pytest.raises(TimeoutError):
                revocation.result(0.2)
        finally:
            resume.set()
        assert upload.result(20).status_code == 201
        revocation.result(20)
    assert get(data, "file").status_code == 401


def test_removing_one_duplicate_contact_preserves_access(data):
    from app.models import CaseContact, User
    from app.routers.case_contacts import remove_case_contact

    with SessionLocal() as db:
        rows = [
            CaseContact(
                case_id=data["cid"],
                contact_id=data["contact"],
                type=ContactType.person,
                name="Synthetic client",
                matter_contact_type="client",
            )
            for _ in range(2)
        ]
        db.add_all(rows)
        db.commit()
        remove_case_contact(
            case_id=data["cid"],
            case_contact_id=rows[0].id,
            user=db.get(User, data["uid"]),
            db=db,
        )
    assert get(data, "file").status_code == 200


def test_reminder_reissues_bound_link_after_rotation(data):
    from app.alert_dispatch import AlertKind

    revoke(data, "version")
    with SessionLocal() as db:
        req = db.get(CanarySignRequest, data["rid"])
        recipient = db.get(CanarySignRecipient, data["recip"])
        sign._notify_recipients(
            db,
            req,
            [recipient],
            kind=AlertKind.canary_sign_reminded,
            event_key=str(uuid.uuid4()),
        )
        db.commit()
        new_token = recipient.sign_token
    assert new_token != data["sign_token"]
    assert (
        data["client"]
        .post("/portal/canary-sign-exchange", json={"sign_token": data["sign_token"]})
        .status_code
        == 401
    )
    assert (
        data["client"]
        .post("/portal/canary-sign-exchange", json={"sign_token": new_token})
        .status_code
        == 200
    )


def test_form_upload_commit_ack_loss_preserves_committed_bytes(data, monkeypatch):
    from app.file_storage import FILES_ROOT
    from sqlalchemy.orm import Session

    original = Session.commit
    once = []

    def uncertain(db):
        if db.info.get("portal_session") and not once:
            once.append(True)
            original(db)
            raise RuntimeError("Synthetic lost commit acknowledgement")
        return original(db)

    monkeypatch.setattr(Session, "commit", uncertain)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        f"/portal/forms/{data['sub']}/upload",
        params={"field_key": "attachments"},
        headers=headers(data),
        files={"upload": ("ack-loss.txt", b"keep committed bytes", "text/plain")},
    )
    assert response.status_code == 500
    with SessionLocal() as db:
        entries = db.get(PortalFormSubmission, data["sub"]).responses["attachments"]
        row = db.get(File, uuid.UUID(entries[0]["file_id"]))
        assert (FILES_ROOT / row.storage_path).read_bytes() == b"keep committed bytes"

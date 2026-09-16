"""Portal form validation/completion and quote respond version conflict."""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuditEvent,
    Base,
    Case,
    CaseStatus,
    Contact,
    ContactType,
    File,
    FileCategory,
    PortalActivityEvent,
    PortalFormFieldType,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
    PortalFormTemplate,
    PortalFormTemplateField,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
)
from app.portal_form_service import _validate_responses, complete_submission
from app.quote_portal_service import respond_to_quote_delivery


def _session(*extra_tables) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    base_tables = (
        User.__table__,
        Case.__table__,
        Contact.__table__,
        File.__table__,
        PortalFormTemplate.__table__,
        PortalFormTemplateField.__table__,
        PortalFormSubmission.__table__,
        QuotePortalDelivery.__table__,
        PortalActivityEvent.__table__,
        AuditEvent.__table__,
    )
    try:
        for table in (*base_tables, *extra_tables):
            table.create(engine, checkfirst=True)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _seed_user_case_contact(db: Session) -> tuple[User, Case, Contact]:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"fee-{uid.hex[:6]}@example.com",
        password_hash="x",
        display_name="Fee Earner",
        initials=f"F{uid.hex[:3].upper()}",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    case = Case(
        id=uuid.uuid4(),
        case_number="000202",
        title="Form matter",
        fee_earner_user_id=uid,
        created_by=uid,
        status=CaseStatus.open,
        portal_enabled=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    contact = Contact(
        id=uuid.uuid4(),
        type=ContactType.person,
        name="Alex Client",
        email="client@example.com",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add_all([user, case, contact])
    db.commit()
    return user, case, contact


def _text_field(*, key: str = "full_name", label: str = "Full name", required: bool = True) -> PortalFormTemplateField:
    return PortalFormTemplateField(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        field_key=key,
        label=label,
        field_type=PortalFormFieldType.text,
        required=required,
        sort_order=0,
        select_options=[],
    )


def _select_field(*, options: list[str], required: bool = True) -> PortalFormTemplateField:
    return PortalFormTemplateField(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        field_key="choice",
        label="Choice",
        field_type=PortalFormFieldType.select,
        required=required,
        sort_order=1,
        select_options=options,
    )


def test_validate_responses_requires_fields() -> None:
    fields = [_text_field(required=True)]
    with pytest.raises(HTTPException) as ei:
        _validate_responses(fields, {})
    assert ei.value.status_code == 422


def test_validate_responses_skips_section_and_optional_blank() -> None:
    section = PortalFormTemplateField(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        field_key="sec",
        label="Section",
        field_type=PortalFormFieldType.section,
        required=False,
        sort_order=0,
        select_options=[],
    )
    optional = _text_field(key="notes", label="Notes", required=False)
    clean = _validate_responses([section, optional], {"notes": "  "})
    assert clean == {}


def test_validate_responses_select_accepts_option() -> None:
    fields = [_select_field(options=["Yes", "No"])]
    assert _validate_responses(fields, {"choice": "Yes"}) == {"choice": "Yes"}


def test_validate_responses_select_rejects_invalid() -> None:
    fields = [_select_field(options=["Yes", "No"])]
    with pytest.raises(HTTPException) as ei:
        _validate_responses(fields, {"choice": "Maybe"})
    assert ei.value.status_code == 422


def test_validate_responses_file_required() -> None:
    field = PortalFormTemplateField(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        field_key="id_scan",
        label="ID scan",
        field_type=PortalFormFieldType.file,
        required=True,
        sort_order=0,
        select_options=[],
    )
    with pytest.raises(HTTPException) as ei:
        _validate_responses([field], {"id_scan": {}})
    assert ei.value.status_code == 422
    file_id = uuid.uuid4()
    clean = _validate_responses([field], {"id_scan": {"file_id": str(file_id), "filename": "id.pdf"}})
    assert clean["id_scan"]["file_id"] == str(file_id)


def test_complete_submission_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    user, case, contact = _seed_user_case_contact(db)
    template = PortalFormTemplate(
        id=uuid.uuid4(),
        name="Client details",
        reference=f"REF-{uuid.uuid4().hex[:8]}",
        owner_id=user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(template)
    db.flush()
    db.add(
        PortalFormTemplateField(
            id=uuid.uuid4(),
            template_id=template.id,
            field_key="full_name",
            label="Full name",
            field_type=PortalFormFieldType.text,
            required=True,
            sort_order=0,
            select_options=[],
        )
    )
    submission = PortalFormSubmission(
        id=uuid.uuid4(),
        case_id=case.id,
        template_id=template.id,
        contact_id=contact.id,
        sent_by_user_id=user.id,
        status=PortalFormSubmissionStatus.pending,
        responses={},
        sent_at=datetime.utcnow(),
    )
    db.add(submission)
    db.commit()

    snapshot_id = uuid.uuid4()
    monkeypatch.setattr(
        "app.portal_form_service._save_snapshot_on_matter",
        lambda *a, **k: SimpleNamespace(id=snapshot_id),
    )
    monkeypatch.setattr("app.portal_form_service.notify_portal_staff_form_completed", lambda *a, **k: None)
    monkeypatch.setattr("app.portal_form_service.log_portal_activity", lambda *a, **k: None)
    monkeypatch.setattr("app.portal_form_service.log_event", lambda *a, **k: None)

    out = complete_submission(
        db,
        submission=submission,
        contact=contact,
        responses_in={"full_name": "Alex Client"},
    )
    db.commit()
    assert out.status == PortalFormSubmissionStatus.completed
    assert out.responses == {"full_name": "Alex Client"}
    assert out.snapshot_file_id == snapshot_id
    assert out.completed_at is not None


def test_complete_submission_rejects_non_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    user, case, contact = _seed_user_case_contact(db)
    template = PortalFormTemplate(
        id=uuid.uuid4(),
        name="Done form",
        reference=f"REF-{uuid.uuid4().hex[:8]}",
        owner_id=user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(template)
    db.flush()
    submission = PortalFormSubmission(
        id=uuid.uuid4(),
        case_id=case.id,
        template_id=template.id,
        contact_id=contact.id,
        sent_by_user_id=user.id,
        status=PortalFormSubmissionStatus.completed,
        responses={"full_name": "x"},
        sent_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db.add(submission)
    db.commit()
    with pytest.raises(HTTPException) as ei:
        complete_submission(db, submission=submission, contact=contact, responses_in={})
    assert ei.value.status_code == 400


def test_respond_to_quote_version_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    user, case, contact = _seed_user_case_contact(db)
    file_row = File(
        id=uuid.uuid4(),
        case_id=case.id,
        owner_id=user.id,
        category=FileCategory.case_document,
        folder_path="Quotes",
        storage_path=f"{case.id}/quote.docx",
        original_filename="Quote.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=100,
        version=2,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(file_row)
    delivery = QuotePortalDelivery(
        id=uuid.uuid4(),
        case_id=case.id,
        file_id=file_row.id,
        contact_id=contact.id,
        sent_by_user_id=user.id,
        file_version_at_send=1,
        status=QuotePortalDeliveryStatus.pending,
        sent_at=datetime.utcnow(),
    )
    db.add(delivery)
    db.commit()

    monkeypatch.setattr("app.quote_portal_service._notify_staff_quote_response", lambda *a, **k: None)
    monkeypatch.setattr("app.quote_portal_service.log_portal_activity", lambda *a, **k: None)
    monkeypatch.setattr("app.quote_portal_service.log_event", lambda *a, **k: None)

    with pytest.raises(HTTPException) as ei:
        respond_to_quote_delivery(
            db,
            delivery=delivery,
            contact=contact,
            accepted=True,
            decline_reason=None,
        )
    assert ei.value.status_code == 409
    db.refresh(delivery)
    assert delivery.status == QuotePortalDeliveryStatus.superseded


def test_respond_to_quote_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    user, case, contact = _seed_user_case_contact(db)
    file_row = File(
        id=uuid.uuid4(),
        case_id=case.id,
        owner_id=user.id,
        category=FileCategory.case_document,
        folder_path="Quotes",
        storage_path=f"{case.id}/quote.docx",
        original_filename="Quote.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=100,
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(file_row)
    delivery = QuotePortalDelivery(
        id=uuid.uuid4(),
        case_id=case.id,
        file_id=file_row.id,
        contact_id=contact.id,
        sent_by_user_id=user.id,
        file_version_at_send=1,
        status=QuotePortalDeliveryStatus.pending,
        sent_at=datetime.utcnow(),
    )
    db.add(delivery)
    db.commit()

    monkeypatch.setattr("app.quote_portal_service._notify_staff_quote_response", lambda *a, **k: None)
    monkeypatch.setattr("app.quote_portal_service.log_portal_activity", lambda *a, **k: None)
    monkeypatch.setattr("app.quote_portal_service.log_event", lambda *a, **k: None)

    out = respond_to_quote_delivery(
        db,
        delivery=delivery,
        contact=contact,
        accepted=True,
        decline_reason=None,
    )
    assert out.status == QuotePortalDeliveryStatus.accepted
    assert out.responded_at is not None

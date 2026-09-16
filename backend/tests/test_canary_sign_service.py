"""Unit tests for Canary Sign service helpers (SQLite + JSONB→JSON)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.canary_sign_service import (
    _form_gate_allows,
    _parse_field_specs,
    _recipient_can_sign_now,
    _validate_field_value,
    claim_form_lock,
    decline_signing,
    mark_expired_if_needed,
    void_signing_request,
)
from app.models import (
    AuditEvent,
    Base,
    CanarySignAuditEvent,
    CanarySignField,
    CanarySignFieldType,
    CanarySignOrderMode,
    CanarySignRecipient,
    CanarySignRecipientStatus,
    CanarySignRequest,
    CanarySignStatus,
    Case,
    CaseLockMode,
    CaseStatus,
    PortalActivityEvent,
    User,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    tables = (
        User.__table__,
        Case.__table__,
        CanarySignRequest.__table__,
        CanarySignRecipient.__table__,
        CanarySignField.__table__,
        CanarySignAuditEvent.__table__,
        PortalActivityEvent.__table__,
        AuditEvent.__table__,
    )
    try:
        for table in tables:
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user(db: Session) -> User:
    uid = uuid.uuid4()
    now = _now()
    row = User(
        id=uid,
        email=f"u-{uid.hex[:8]}@example.com",
        password_hash="x",
        display_name="Staff",
        initials=f"S{uid.hex[:3].upper()}",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _case(db: Session, fee: User) -> Case:
    now = _now()
    row = Case(
        id=uuid.uuid4(),
        case_number=f"CS/{uuid.uuid4().hex[:6]}",
        title="Sign test matter",
        fee_earner_user_id=fee.id,
        created_by=fee.id,
        status=CaseStatus.open,
        lock_mode=CaseLockMode.none,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _request(
    db: Session,
    *,
    case: Case,
    status: CanarySignStatus = CanarySignStatus.pending,
    order_mode: CanarySignOrderMode = CanarySignOrderMode.parallel,
    expires_at: datetime | None = None,
    has_fillable_form: bool = False,
    form_locked_by_recipient_id: uuid.UUID | None = None,
    form_completed_at: datetime | None = None,
) -> CanarySignRequest:
    now = _now()
    row = CanarySignRequest(
        id=uuid.uuid4(),
        case_id=case.id,
        source_file_id=uuid.uuid4(),
        subject="Please sign",
        status=status,
        order_mode=order_mode,
        expires_at=expires_at or (now + timedelta(days=7)),
        has_fillable_form=has_fillable_form,
        form_locked_by_recipient_id=form_locked_by_recipient_id,
        form_completed_at=form_completed_at,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _recipient(
    db: Session,
    req: CanarySignRequest,
    *,
    routing_order: int = 1,
    status: CanarySignRecipientStatus = CanarySignRecipientStatus.pending,
    name: str = "Alice",
) -> CanarySignRecipient:
    row = CanarySignRecipient(
        id=uuid.uuid4(),
        signing_request_id=req.id,
        name=name,
        email=f"{name.lower()}@example.com",
        routing_order=routing_order,
        sign_token=secrets_token(),
        status=status,
        created_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def secrets_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]


def _field(
    *,
    field_type: CanarySignFieldType,
    required: bool = True,
) -> CanarySignField:
    return CanarySignField(
        id=uuid.uuid4(),
        signing_request_id=uuid.uuid4(),
        recipient_id=uuid.uuid4(),
        field_type=field_type,
        required=required,
        sort_order=0,
        placement_mode="fixed",
    )


# --- _parse_field_specs ---


def test_parse_field_specs_empty_raises() -> None:
    db = _session()
    recip = CanarySignRecipient(
        id=uuid.uuid4(),
        signing_request_id=uuid.uuid4(),
        name="A",
        email="a@example.com",
        routing_order=1,
        sign_token=secrets_token(),
    )
    with pytest.raises(HTTPException) as exc:
        _parse_field_specs(db, request_id=uuid.uuid4(), recipients=[recip], fields_specs=None)
    assert exc.value.status_code == 400
    assert "at least one field" in str(exc.value.detail).lower()


def test_parse_field_specs_invalid_type() -> None:
    db = _session()
    recip = CanarySignRecipient(
        id=uuid.uuid4(),
        signing_request_id=uuid.uuid4(),
        name="A",
        email="a@example.com",
        routing_order=1,
        sign_token=secrets_token(),
    )
    with pytest.raises(HTTPException) as exc:
        _parse_field_specs(
            db,
            request_id=uuid.uuid4(),
            recipients=[recip],
            fields_specs=[{"field_type": "bogus", "page": 1, "x_pct": 0, "y_pct": 0, "w_pct": 10, "h_pct": 5}],
        )
    assert exc.value.status_code == 400
    assert "Invalid field_type" in str(exc.value.detail)


def test_parse_field_specs_happy() -> None:
    db = _session()
    rid = uuid.uuid4()
    recip = CanarySignRecipient(
        id=uuid.uuid4(),
        signing_request_id=rid,
        name="A",
        email="a@example.com",
        routing_order=1,
        sign_token=secrets_token(),
    )
    fields = _parse_field_specs(
        db,
        request_id=rid,
        recipients=[recip],
        fields_specs=[
            {
                "field_type": "signature",
                "page": 1,
                "x_pct": 10,
                "y_pct": 20,
                "w_pct": 30,
                "h_pct": 8,
                "label": "Sign here",
            }
        ],
    )
    assert len(fields) == 1
    assert fields[0].field_type == CanarySignFieldType.signature
    assert fields[0].recipient_id == recip.id
    assert fields[0].page == 1
    assert fields[0].label == "Sign here"


# --- _validate_field_value ---


def test_validate_signature_requires_image_or_text() -> None:
    field = _field(field_type=CanarySignFieldType.signature)
    with pytest.raises(HTTPException) as exc:
        _validate_field_value(field, {})
    assert exc.value.status_code == 400


def test_validate_signature_accepts_image() -> None:
    field = _field(field_type=CanarySignFieldType.signature)
    out = _validate_field_value(field, {"image_b64": "abc"})
    assert out["image_b64"] == "abc"


def test_validate_checkbox_required() -> None:
    field = _field(field_type=CanarySignFieldType.checkbox)
    with pytest.raises(HTTPException) as exc:
        _validate_field_value(field, {})
    assert "checkbox" in str(exc.value.detail).lower()
    assert _validate_field_value(field, {"checked": True})["checked"] is True


def test_validate_text_field_required() -> None:
    field = _field(field_type=CanarySignFieldType.printed_name)
    with pytest.raises(HTTPException):
        _validate_field_value(field, {"text": "  "})
    assert _validate_field_value(field, {"text": "Jane Doe"})["text"] == "Jane Doe"


# --- mark_expired_if_needed ---


def test_mark_expired_if_needed_marks_past_expiry() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case, expires_at=_now() - timedelta(hours=1))
    out = mark_expired_if_needed(db, req)
    assert out.status == CanarySignStatus.expired
    assert out.status_detail == "Expired"


def test_mark_expired_if_needed_leaves_future() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case, expires_at=_now() + timedelta(days=1))
    out = mark_expired_if_needed(db, req)
    assert out.status == CanarySignStatus.pending


def test_mark_expired_skips_non_pending() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case, status=CanarySignStatus.completed, expires_at=_now() - timedelta(days=1))
    out = mark_expired_if_needed(db, req)
    assert out.status == CanarySignStatus.completed


# --- sequential / parallel + form gate ---


def test_recipient_can_sign_parallel() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case, order_mode=CanarySignOrderMode.parallel)
    r1 = _recipient(db, req, routing_order=1)
    r2 = _recipient(db, req, routing_order=2, name="Bob")
    assert _recipient_can_sign_now(db, req, r1) is True
    assert _recipient_can_sign_now(db, req, r2) is True


def test_recipient_can_sign_sequential_blocks_second() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case, order_mode=CanarySignOrderMode.sequential)
    r1 = _recipient(db, req, routing_order=1)
    r2 = _recipient(db, req, routing_order=2, name="Bob")
    assert _recipient_can_sign_now(db, req, r1) is True
    assert _recipient_can_sign_now(db, req, r2) is False
    r1.status = CanarySignRecipientStatus.signed
    db.add(r1)
    db.commit()
    assert _recipient_can_sign_now(db, req, r2) is True


def test_form_gate_allows_when_unlocked_or_locker() -> None:
    req = CanarySignRequest(
        id=uuid.uuid4(),
        case_id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        subject="x",
        status=CanarySignStatus.pending,
        expires_at=_now() + timedelta(days=1),
        has_fillable_form=True,
        form_locked_by_recipient_id=None,
    )
    recip = CanarySignRecipient(
        id=uuid.uuid4(),
        signing_request_id=req.id,
        name="A",
        email="a@example.com",
        routing_order=1,
        sign_token=secrets_token(),
    )
    assert _form_gate_allows(req, recip) is True

    other = uuid.uuid4()
    req.form_locked_by_recipient_id = other
    assert _form_gate_allows(req, recip) is False
    req.form_locked_by_recipient_id = recip.id
    assert _form_gate_allows(req, recip) is True
    req.form_completed_at = _now()
    assert _form_gate_allows(req, recip) is True


# --- void / claim / decline ---


def test_void_signing_request_happy() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case)
    out = void_signing_request(db, req=req, actor=user, reason="Withdrawn")
    assert out.status == CanarySignStatus.voided
    assert out.status_detail == "Withdrawn"
    assert out.voided_at is not None


def test_void_signing_request_bad_state() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case, status=CanarySignStatus.completed)
    with pytest.raises(HTTPException) as exc:
        void_signing_request(db, req=req, actor=user, reason="nope")
    assert exc.value.status_code == 400


def test_claim_form_lock_first_then_409() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case, has_fillable_form=True)
    r1 = _recipient(db, req, name="Alice")
    r2 = _recipient(db, req, routing_order=2, name="Bob")
    out = claim_form_lock(db, req, r1)
    assert out.form_locked_by_recipient_id == r1.id
    with pytest.raises(HTTPException) as exc:
        claim_form_lock(db, req, r2)
    assert exc.value.status_code == 409


def test_decline_signing_happy() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case)
    recip = _recipient(db, req)
    with patch("app.canary_sign_service._notify_staff_declined"):
        out = decline_signing(db, req, recip, reason="No thanks")
    assert out.status == CanarySignStatus.declined
    db.refresh(recip)
    assert recip.status == CanarySignRecipientStatus.declined
    assert recip.decline_reason == "No thanks"


def test_decline_signing_already_signed() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    req = _request(db, case=case)
    recip = _recipient(db, req, status=CanarySignRecipientStatus.signed)
    with pytest.raises(HTTPException) as exc:
        decline_signing(db, req, recip, reason="late")
    assert exc.value.status_code == 400
    assert "Already signed" in str(exc.value.detail)

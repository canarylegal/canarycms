"""Transactional staff notifications and an explicitly invoked, fail-closed dispatcher."""

import hashlib
import json
import smtplib
import uuid
from dataclasses import asdict
from datetime import timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.audit import log_event
from app.db import SessionLocal
from app.deps import require_case_access
from app.admin_access import user_effective_admin
from app.email_crypt import encrypt_password, decrypt_password
from app.firm_email_service import (
    FirmEmailMessage,
    resolve_alert_transport,
    send_firm_email,
)
from app.models import NotificationOutbox, NotificationAttempt, User
from app.timeutil import utcnow
from app.upload_receipts import lock_receipt

STAFF_KINDS = frozenset(
    (
        "portal_staff_upload",
        "portal_form_completed",
        "portal_quote_accepted",
        "portal_quote_declined",
        "calendar_event_reminder",
        "docusign_sign_sent_staff",
        "docusign_sign_completed_staff",
        "casera_search_result",
        "invoice_approved",
        "invoice_rejected",
        "anticipated_payment_approved",
        "anticipated_payment_rejected",
        "anticipated_payment_amended",
        "canary_sign_sent_staff",
        "canary_sign_completed_staff",
        "canary_sign_declined_staff",
    )
)
STALE_AFTER = timedelta(minutes=15)


def _audit(db, row, actor_id, action, **meta):
    log_event(
        db,
        actor_user_id=actor_id,
        action=f"notification.{action}",
        entity_type="notification_outbox",
        entity_id=str(row.id),
        meta={
            "state": row.state,
            "version": row.version,
            "kind": row.kind,
            "attempt_id": str(row.attempt_id) if row.attempt_id else None,
            **meta,
        },
    )


def enqueue_staff(
    db, *, kind, event_key, case_id, recipient_user_id, context, actor_id
):
    """No commit or network I/O: the caller commits the business change and this row."""
    from app.alert_dispatch import render_alert, AlertKind

    kind = getattr(kind, "value", kind)
    if kind not in STAFF_KINDS:
        raise ValueError(
            "Only the explicitly supported staff alerts may enter this outbox"
        )
    if not event_key or len(event_key) > 240:
        raise ValueError("A bounded stable event identity is required")
    if case_id is None and kind != "calendar_event_reminder":
        raise ValueError("Matter staff alerts require a case identity")
    recipient = db.get(User, recipient_user_id)
    if (
        recipient is None
        or not recipient.is_active
        or not (recipient.email or "").strip()
    ):
        return None
    identity = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"canary:staff:{case_id}:{kind}:{event_key}:{recipient_user_id}",
    )
    lock_receipt(db, identity)
    existing = db.get(NotificationOutbox, identity)
    if existing:
        return existing
    message = render_alert(
        db, AlertKind(kind), to_email=recipient.email.strip(), context=context
    )
    if message is None:
        raise ValueError("Staff alert cannot be rendered")
    raw = json.dumps(asdict(message), sort_keys=True, separators=(",", ":"))
    if len(raw.encode()) > 256 * 1024:
        raise ValueError("Staff notification exceeds supported size")
    row = NotificationOutbox(
        id=identity,
        kind=kind,
        event_key=event_key,
        case_id=case_id,
        recipient_user_id=recipient_user_id,
        payload_enc=encrypt_password(raw),
        payload_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        state="pending",
        version=1,
    )
    db.add(row)
    db.flush()
    _audit(db, row, actor_id, "queued", payload_sha256=row.payload_sha256)
    return row


def _admin(db, actor_id):
    actor = db.get(User, actor_id)
    if actor is None or not actor.is_active or not user_effective_admin(actor, db):
        raise HTTPException(
            403, "An active administrator is required for notification operations"
        )
    return actor


def _locked(db, notification_id):
    row = db.scalar(
        select(NotificationOutbox)
        .where(NotificationOutbox.id == notification_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise HTTPException(404, "Notification not found")
    return row


def summary(row):
    return {
        "id": str(row.id),
        "kind": row.kind,
        "state": row.state,
        "version": row.version,
        "attempt_id": str(row.attempt_id) if row.attempt_id else None,
        "last_code": row.last_code,
    }


def _message(row):
    raw = decrypt_password(row.payload_enc)
    if hashlib.sha256(raw.encode()).hexdigest() != row.payload_sha256:
        raise ValueError("Payload integrity failed")
    values = json.loads(raw)
    values["notification_id"] = str(row.id)
    return FirmEmailMessage(**values)


def deliver(
    notification_id, *, actor_id, session_factory=SessionLocal, sender=send_firm_email
):
    """Claim durably before I/O. Ambiguous results never become automatically retryable."""
    with session_factory() as db:
        _admin(db, actor_id)
        row = _locked(db, notification_id)
        if row.kind not in STAFF_KINDS:
            raise HTTPException(400, "Use the Canary Sign delivery command for recipient messages")
        if row.state != "pending":
            return summary(row)
        code = None
        message = None
        transport = None
        try:
            message = _message(row)
        except Exception:
            code = "payload_invalid"
        if code is None:
            recipient = db.get(User, row.recipient_user_id)
            if (
                recipient is None
                or not recipient.is_active
                or (recipient.email or "").strip() != message.to_email
            ):
                code = "recipient_changed_or_inactive"
            else:
                try:
                    if row.kind == "calendar_event_reminder":
                        from app.calendar_email_alert_service import (
                            require_reminder_access,
                        )

                        require_reminder_access(db, row, recipient)
                    else:
                        require_case_access(row.case_id, recipient, db)
                except HTTPException:
                    code = "recipient_access_denied"
        if code is None:
            try:
                transport = resolve_alert_transport(db)
            except Exception:
                code = "transport_unavailable"
            if transport is None:
                code = code or "transport_disabled_or_unconfigured"
        token = uuid.uuid4()
        now = utcnow()
        row.attempt_id = token
        row.version += 1
        row.updated_at = now
        row.last_code = code
        row.state = "failed" if code else "sending"
        attempt = NotificationAttempt(
            id=token,
            notification_id=row.id,
            operator_id=actor_id,
            state=row.state,
            transport=transport,
            code=code,
            started_at=now,
            finished_at=now if code else None,
        )
        db.add(attempt)
        _audit(
            db,
            row,
            actor_id,
            "failed" if code else "attempt_started",
            code=code,
            transport=transport,
        )
        result = summary(row)
        db.commit()  # No external call unless its attempt and audit were committed.
    if code:
        return result
    outcome = "sent"
    code = "provider_accepted"
    try:
        with session_factory() as send_db:
            transport = sender(send_db, message)
    except (
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPRecipientsRefused,
        smtplib.SMTPDataError,
    ):
        outcome = "failed"
        code = "provider_rejected"
    except Exception:
        outcome = "uncertain"
        code = "transport_outcome_unknown"
    with session_factory() as db:
        row = _locked(db, notification_id)
        # A stale-attempt review must not be overwritten by a late worker.
        if row.state != "sending" or row.attempt_id != token:
            _audit(
                db,
                row,
                actor_id,
                "late_result",
                reported_outcome=outcome,
                reported_attempt_id=str(token),
            )
            result = summary(row)
            db.commit()
            return result
        row.state = outcome
        row.last_code = code
        row.version += 1
        row.updated_at = utcnow()
        attempt = db.get(NotificationAttempt, token)
        attempt.state = outcome
        attempt.code = code
        attempt.finished_at = utcnow()
        if isinstance(transport, str):
            attempt.transport = transport
        _audit(db, row, actor_id, outcome, code=code)
        result = summary(row)
        db.commit()  # Failure here leaves the persisted claim 'sending', never a false success.
        return result


def review(
    db,
    notification_id,
    *,
    actor_id,
    expected_version,
    action,
    reason,
    acknowledge_uncertain=False,
):
    _admin(db, actor_id)
    if not reason.strip() or len(reason) > 1000:
        raise HTTPException(400, "A review reason of 1–1000 characters is required")
    row = _locked(db, notification_id)
    if row.version != expected_version:
        raise HTTPException(409, "Notification changed; review its current state")
    old = row.state
    if action == "mark-uncertain":
        updated = row.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if old != "sending" or utcnow() - updated < STALE_AFTER:
            raise HTTPException(
                409,
                "Only an attempt stale for at least 15 minutes may be marked uncertain",
            )
        row.state = "uncertain"
        row.last_code = "stale_attempt"
        attempt = db.get(NotificationAttempt, row.attempt_id)
        if attempt:
            attempt.state = "uncertain"
            attempt.code = "stale_attempt"
            attempt.finished_at = utcnow()
    elif action == "retry":
        if old not in ("failed", "uncertain"):
            raise HTTPException(
                409, "Only failed or reviewed uncertain deliveries can be retried"
            )
        if old == "uncertain" and not acknowledge_uncertain:
            raise HTTPException(
                409,
                "Review provider evidence and explicitly acknowledge the duplicate-delivery risk",
            )
        row.state = "pending"
        row.last_code = None
    elif action == "cancel":
        if old not in ("pending", "failed", "uncertain"):
            raise HTTPException(
                409, "An active or accepted attempt cannot be cancelled"
            )
        row.state = "cancelled"
        row.last_code = "operator_cancelled"
    else:
        raise HTTPException(400, "Unknown review action")
    row.version += 1
    row.updated_at = utcnow()
    _audit(
        db,
        row,
        actor_id,
        action.replace("-", "_"),
        previous_state=old,
        reason=reason.strip(),
        acknowledge_uncertain=acknowledge_uncertain,
    )
    return summary(row)

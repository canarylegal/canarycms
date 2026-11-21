"""Durable recipient mail, dispatched on demand only. Never retries an uncertain send."""

import hashlib
import json
import logging
import smtplib
import uuid
from dataclasses import asdict
from datetime import timezone
from sqlalchemy import select, text, func
from fastapi import HTTPException
from app.db import SessionLocal
from app.models import (
    NotificationOutbox,
    NotificationAttempt,
    CanarySignRequest,
    CanarySignRecipient,
    ContactPortalAccess,
    Contact,
    User,
)
from app.notification_outbox import _locked, _audit, _message, summary, STALE_AFTER
from app.email_crypt import encrypt_password, decrypt_password
from app.firm_email_service import resolve_alert_transport, send_firm_email
from app.deps import require_case_access
from app.portal_case import require_case_portal_enabled, firm_canary_sign_enabled
from app.portal_service import portal_access_is_active
from app.timeutil import utcnow

KINDS = frozenset(("canary_sign_requested", "canary_sign_reminded"))
log = logging.getLogger(__name__)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def operation(db, key, actor_id, payload):
    """A stable audit-event ID identifies an explicit API retry, without storing secret payloads."""
    from app.models import CanarySignAuditEvent

    if key is None:
        return None, None
    identity = uuid.uuid5(uuid.NAMESPACE_URL, f"canary:sign-operation:{actor_id}:{key}")
    if db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": identity.int & ((1 << 63) - 1)},
        )
    prior = db.get(CanarySignAuditEvent, identity)
    digest = fingerprint(payload)
    if prior:
        if (prior.detail or {}).get("operation_fingerprint") != digest:
            raise HTTPException(409, "This signing retry has different content")
        req = db.get(CanarySignRequest, prior.signing_request_id)
        if req is None:
            raise HTTPException(409, "Original signing request is unavailable")
        return identity, req
    return identity, None


def enqueue(db, req, recipient, *, kind, context, event_key):
    from app.alert_dispatch import render_alert, AlertKind

    kind = getattr(kind, "value", kind)
    if kind not in KINDS:
        raise ValueError("Unsupported signing delivery kind")
    identity = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"canary:sign-mail:{req.id}:{recipient.id}:{kind}:{event_key}",
    )
    existing = db.get(NotificationOutbox, identity)
    if existing:
        return existing
    message = render_alert(
        db, AlertKind(kind), to_email=recipient.email, context=context
    )
    if message is None:
        raise HTTPException(400, "Signing notification could not be prepared")
    access = (
        db.scalar(
            select(ContactPortalAccess).where(
                ContactPortalAccess.contact_id == recipient.contact_id
            )
        )
        if recipient.contact_id
        else None
    )
    contact = db.get(Contact, recipient.contact_id) if recipient.contact_id else None
    binding = {
        "contact_id": str(recipient.contact_id),
        "contact_email": getattr(contact, "email", None),
        "token_sha256": hashlib.sha256(recipient.sign_token.encode()).hexdigest(),
        "access_code_sha256": access.code_sha256 if access else None,
        "session_version": access.session_version if access else None,
    }
    raw = json.dumps(asdict(message), sort_keys=True, separators=(",", ":"))
    row = NotificationOutbox(
        id=identity,
        kind=kind,
        event_key=str(event_key),
        case_id=req.case_id,
        recipient_user_id=None,
        signing_request_id=req.id,
        signing_recipient_id=recipient.id,
        binding_enc=encrypt_password(json.dumps(binding, sort_keys=True)),
        payload_enc=encrypt_password(raw),
        payload_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        state="pending",
        version=1,
    )
    db.add(row)
    db.flush()
    _audit(db, row, req.sent_by_user_id, "queued", payload_sha256=row.payload_sha256)
    return row


def _eligibility(db, row, req, message):
    if req is None or req.case_id != row.case_id:
        return "request_unavailable"
    expires = (
        req.expires_at.replace(tzinfo=timezone.utc)
        if req.expires_at.tzinfo is None
        else req.expires_at
    )
    if req.status.value != "pending":
        return "request_inactive"
    if expires <= utcnow():
        return "request_expired"
    if not firm_canary_sign_enabled(db):
        return "signing_disabled"
    try:
        require_case_portal_enabled(db, req.case_id)
    except HTTPException:
        return "portal_disabled"
    recipient = db.get(CanarySignRecipient, row.signing_recipient_id)
    if (
        not recipient
        or recipient.signing_request_id != req.id
        or recipient.status.value not in ("pending", "viewed")
    ):
        return "recipient_inactive"
    if recipient.email.strip() != message.to_email:
        return "recipient_changed"
    try:
        binding = json.loads(decrypt_password(row.binding_enc))
    except Exception:
        return "binding_invalid"
    if binding["token_sha256"] != hashlib.sha256(
        recipient.sign_token.encode()
    ).hexdigest() or binding["contact_id"] != str(recipient.contact_id):
        return "recipient_changed"
    contact = db.get(Contact, recipient.contact_id) if recipient.contact_id else None
    access = (
        db.scalar(
            select(ContactPortalAccess).where(
                ContactPortalAccess.contact_id == recipient.contact_id
            )
        )
        if contact
        else None
    )
    if not access or not portal_access_is_active(access):
        return "portal_access_inactive"
    if (
        contact.email != binding["contact_email"]
        or access.code_sha256 != binding["access_code_sha256"]
        or access.session_version != binding["session_version"]
    ):
        return "portal_access_changed"
    if req.order_mode.value == "sequential":
        waiting = db.scalar(
            select(func.min(CanarySignRecipient.routing_order)).where(
                CanarySignRecipient.signing_request_id == req.id,
                CanarySignRecipient.status.notin_(["signed", "declined"]),
            )
        )
        if recipient.routing_order != waiting:
            return "waiting_turn"
    return None


def _request_lock(db, request_id):
    return db.scalar(
        select(CanarySignRequest)
        .where(CanarySignRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _actor(db, actor_id, case_id):
    actor = db.get(User, actor_id)
    if not actor or not actor.is_active:
        raise HTTPException(403, "Active staff member required")
    require_case_access(case_id, actor, db)


def deliver(notification_id, *, actor_id, session_factory=SessionLocal, sender=None):
    sender = sender or send_firm_email
    with session_factory() as db:
        initial = db.get(NotificationOutbox, notification_id)
        if not initial or initial.kind not in KINDS:
            raise HTTPException(404, "Signing delivery not found")
        _actor(db, actor_id, initial.case_id)
        # Fast-path lets a competing operator observe a durable in-flight claim.
        if initial.state != "pending":
            return summary(initial)
        req = _request_lock(db, initial.signing_request_id)
        row = _locked(db, notification_id)
        if row.state != "pending":
            return summary(row)
        code = None
        try:
            message = _message(row)
        except Exception:
            code = "payload_invalid"
        if code is None:
            code = _eligibility(db, row, req, message)
        if code == "waiting_turn":
            return {**summary(row), "eligibility": code}
        transport = None
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
        row.state = (
            (
                "failed"
                if code.startswith(("transport_", "payload_", "binding_"))
                else "cancelled"
            )
            if code
            else "sending"
        )
        db.add(
            NotificationAttempt(
                id=token,
                notification_id=row.id,
                operator_id=actor_id,
                state=row.state,
                transport=transport,
                code=code,
                started_at=now,
                finished_at=now if code else None,
            )
        )
        _audit(
            db, row, actor_id, "attempt_started" if not code else row.state, code=code
        )
        result = summary(row)
        request_id = row.signing_request_id
        db.commit()  # Claim and evidence survive process death before any provider call.
    if code:
        return result
    outcome, code = "sent", "provider_accepted"
    # Recheck after the claim gap and serialize cancellation/signing against the provider call.
    with session_factory() as sending:
        req = _request_lock(sending, request_id)
        current = sending.get(NotificationOutbox, notification_id)
        if current.state != "sending" or current.attempt_id != token:
            return summary(current)
        try:
            _actor(sending, actor_id, current.case_id)
            code = _eligibility(sending, current, req, message)
            if code:
                outcome = "cancelled"
            else:
                transport = sender(sending, message)
                code = "provider_accepted"
        except HTTPException:
            outcome, code = "cancelled", "operator_access_revoked"
        except (
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPRecipientsRefused,
            smtplib.SMTPDataError,
        ):
            outcome, code = "failed", "provider_rejected"
        except Exception:
            outcome, code = "uncertain", "transport_outcome_unknown"
        # Retain the request lock until the provider call finishes. No external settings are changed here.
        sending.rollback()
    with session_factory() as db:
        row = _locked(db, notification_id)
        if row.state != "sending" or row.attempt_id != token:
            _audit(
                db,
                row,
                actor_id,
                "late_result",
                reported_outcome=outcome,
                reported_attempt_id=str(token),
            )
        else:
            row.state = outcome
            row.last_code = code
            row.version += 1
            row.updated_at = utcnow()
            attempt = db.get(NotificationAttempt, token)
            attempt.state = outcome
            attempt.code = code
            attempt.finished_at = utcnow()
            _audit(db, row, actor_id, outcome, code=code)
        result = summary(row)
        db.commit()
        return result


def dispatch_request(request_id, actor_id):
    """Best effort on-demand wakeup after a committed user action; queue survives failure."""
    try:
        with SessionLocal() as db:
            ids = list(
                db.scalars(
                    select(NotificationOutbox.id)
                    .where(
                        NotificationOutbox.signing_request_id == request_id,
                        NotificationOutbox.kind.in_(KINDS),
                        NotificationOutbox.state == "pending",
                    )
                    .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
                )
            )
        for identity in ids:
            try:
                deliver(identity, actor_id=actor_id)
            except Exception:
                log.warning(
                    "Canary Sign delivery requires review: notification_id=%s", identity
                )
    except Exception:
        log.warning(
            "Canary Sign delivery wakeup requires review: request_id=%s", request_id
        )


def diagnostics(db, *, request_id=None, limit=200):
    from app.notification_outbox import STALE_AFTER

    if not 1 <= limit <= 1000:
        raise ValueError("Diagnostic limit must be between 1 and 1000")
    filters = [NotificationOutbox.kind.in_(KINDS)]
    if request_id is not None:
        filters.append(NotificationOutbox.signing_request_id == request_id)
    states = dict(
        db.execute(
            select(NotificationOutbox.state, func.count())
            .where(*filters)
            .group_by(NotificationOutbox.state)
        ).all()
    )
    rows = []
    for row in db.scalars(
        select(NotificationOutbox)
        .where(*filters)
        .order_by(
            NotificationOutbox.state.in_(
                ["pending", "sending", "failed", "uncertain"]
            ).desc(),
            NotificationOutbox.created_at,
            NotificationOutbox.id,
        )
        .limit(limit)
    ):
        item = {
            **summary(row),
            "request_id": str(row.signing_request_id),
            "recipient_id": str(row.signing_recipient_id),
        }
        item["attempts"] = [
            {"id": str(a.id), "state": a.state, "code": a.code}
            for a in db.scalars(
                select(NotificationAttempt)
                .where(NotificationAttempt.notification_id == row.id)
                .order_by(NotificationAttempt.started_at)
            )
        ]
        if row.state == "pending":
            try:
                item["eligibility"] = (
                    _eligibility(
                        db,
                        row,
                        db.get(CanarySignRequest, row.signing_request_id),
                        _message(row),
                    )
                    or "eligible"
                )
            except Exception:
                item["eligibility"] = "payload_or_binding_invalid"
        updated = (
            row.updated_at.replace(tzinfo=timezone.utc)
            if row.updated_at.tzinfo is None
            else row.updated_at
        )
        item["stale_sending"] = (
            row.state == "sending" and utcnow() - updated >= STALE_AFTER
        )
        rows.append(item)
    return {
        "deliveries": rows,
        "states": states,
        "total": sum(states.values()),
        "has_more": sum(states.values()) > len(rows),
        "sent_means": "provider_accepted",
        "automatic_retries": False,
        "delivery_mode": "on-demand",
    }

"""Core's opt-in local adapter boundary; all actions are explicit, never scheduled.

Mutation methods own their transaction; call with a dedicated Session. Trusted
adapter validators must reject credential-bearing payloads/results. Application
callbacks may stage database changes only: no commit, network or filesystem I/O.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
import re
import uuid
from typing import Callable
from sqlalchemy import select, event
from sqlalchemy.orm import Session
from app.audit import log_event
from app.deps import require_case_access
from app.email_crypt import encrypt_password, decrypt_password
from app.models import User
from app.models.commercial_connection import CommercialConnection, CommercialCredential, CommercialOperation, CommercialApplication
from app.commercial_transport import ConnectionError, Transport, configured_origin, VERSION, MAX_BYTES


@dataclass(frozen=True)
class Adapter:
    credential_key: str
    validate_request: Callable[[dict], dict]
    validate_result: Callable[[dict], dict]
    apply: Callable[[Session, CommercialOperation, dict], None]


# Populated explicitly by reviewed local packages. No provider is migrated by this foundation.
ADAPTERS: dict[str, Adapter] = {}


def encode(value: dict) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ConnectionError("invalid_payload") from None
    if len(raw.encode()) > MAX_BYTES:
        raise ConnectionError("payload_too_large")
    return raw


def reject_credentials(value):
    # Defence in depth: adapters still own strict, operation-specific schemas.
    forbidden = {"password", "credentials", "secret", "clientsecret", "developerkey", "developersecret", "accesstoken", "refreshtoken", "authorization", "activationcode", "installationsecret"}
    if isinstance(value, dict):
        for key, item in value.items():
            if re.sub(r"[^a-z]", "", str(key).lower()) in forbidden:
                raise ConnectionError("credentials_in_payload")
            reject_credentials(item)
    elif isinstance(value, list):
        for item in value:
            reject_credentials(item)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def encrypt(raw: str) -> str:
    if not os.getenv("DATA_ENCRYPTION_KEY"):
        raise ConnectionError("local_encryption_required")
    return encrypt_password(raw)


def audit(db, actor, action, entity):
    log_event(db, actor_user_id=actor.id, action="commercial.connection." + action,
              entity_type="commercial_connection", entity_id=str(entity))


def locked_connection(db: Session) -> CommercialConnection:
    row = db.scalar(select(CommercialConnection).where(CommercialConnection.id == 1).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise ConnectionError("not_activated")
    return row


def status(db: Session) -> dict:
    row = db.get(CommercialConnection, 1)
    return {"enabled": os.getenv("CANARY_COMMERCIAL_SERVICE_ENABLED") == "1",
            "connected": bool(row and row.secret_enc), "version": row.version if row else 0,
            "installation_id": str(row.installation_id) if row else None,
            "tenant_id": str(row.tenant_id) if row and row.tenant_id else None,
            "contract_version": VERSION}


def activate(db: Session, actor: User, code: str, expected_version: int) -> dict:
    origin = configured_origin()
    encrypt("activation-key-check")
    if not code or len(code) > 512:
        raise ConnectionError("invalid_activation_code")
    row = db.get(CommercialConnection, 1)
    if row is None:
        if expected_version != 0:
            raise ConnectionError("version_conflict")
        # Persist installation identity before contacting service. A concurrent first
        # activation loses the PK race; it must reload, never invent a second identity.
        row = CommercialConnection(id=1, installation_id=uuid.uuid4(), version=0)
        db.add(row)
        db.commit()
    row = locked_connection(db)
    if row.version != expected_version:
        raise ConnectionError("version_conflict")
    data = Transport(origin).request("POST", "/v1/installations/activate", {
        "contract_version": VERSION, "installation_id": str(row.installation_id),
        "expected_tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "activation_code": code})
    try:
        tenant = uuid.UUID(data["tenant_id"])
        secret = data["installation_secret"]
        if data["contract_version"] != VERSION: raise ValueError()
        if data["installation_id"] != str(row.installation_id): raise ValueError()
        if not isinstance(secret, str) or not 32 <= len(secret) <= 4096: raise ValueError()
        if row.tenant_id is not None and row.tenant_id != tenant: raise ValueError()
        if row.origin is not None and row.origin != origin: raise ValueError()
    except (KeyError, ValueError, TypeError, AssertionError):
        raise ConnectionError("invalid_response") from None
    row.origin, row.tenant_id, row.secret_enc = origin, tenant, encrypt(secret)
    row.version += 1
    audit(db, actor, "activated", row.installation_id)
    db.commit()
    return status(db)


def disconnect(db: Session, actor: User, expected_version: int) -> dict:
    row = locked_connection(db)
    if row.version != expected_version:
        raise ConnectionError("version_conflict")
    row.secret_enc = None
    row.version += 1
    audit(db, actor, "disconnected", row.installation_id)
    db.commit()
    return status(db)


def credential_status(db: Session, key: str) -> dict:
    row = db.get(CommercialCredential, key, populate_existing=True)
    return {"key": key, "version": row.version if row else 0, "configured": bool(row and row.secret_enc)}


def set_credential(db: Session, actor: User, key: str, value: dict | None, expected_version: int) -> dict:
    # Serialize credential mutations against operations and activation.
    locked_connection(db)
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", key):
        raise ConnectionError("invalid_credential_key")
    row = db.get(CommercialCredential, key, populate_existing=True)
    if (row.version if row else 0) != expected_version:
        raise ConnectionError("version_conflict")
    secret = encrypt(encode(value)) if value is not None else None
    if row is None:
        row = CommercialCredential(key=key, version=0)
        db.add(row)
    row.version += 1
    row.secret_enc = secret
    audit(db, actor, "credential_updated" if secret else "credential_revoked", key)
    db.commit()
    return credential_status(db, key)


def connection(db: Session) -> CommercialConnection:
    origin = configured_origin()
    row = locked_connection(db)
    if not row.secret_enc or row.origin != origin:
        raise ConnectionError("not_connected")
    return row


def prepare(db: Session, actor: User, case_id: uuid.UUID, adapter_name: str, operation_id: uuid.UUID, payload: dict) -> CommercialOperation:
    require_case_access(case_id, actor, db)
    adapter = ADAPTERS.get(adapter_name)
    if adapter is None:
        raise ConnectionError("unsupported_adapter")
    payload = adapter.validate_request(payload)
    reject_credentials(payload)
    raw = encode(payload)
    row = connection(db)
    fingerprint = digest(encode({"installation_id": str(row.installation_id), "tenant_id": str(row.tenant_id),
                                 "case_id": str(case_id), "adapter": adapter_name, "payload": json.loads(raw)}))
    existing = db.get(CommercialOperation, operation_id)
    if existing:
        if existing.fingerprint != fingerprint:
            raise ConnectionError("operation_conflict")
        return existing
    op = CommercialOperation(id=operation_id, installation_id=row.installation_id, tenant_id=row.tenant_id,
        case_id=case_id, actor_id=actor.id, adapter=adapter_name, credential_key=adapter.credential_key,
        fingerprint=fingerprint, payload_enc=encrypt(raw), state="pending")
    db.add(op)
    audit(db, actor, "prepared", op.id)
    db.commit()
    return op


def owned_operation(db: Session, actor: User, op_id: uuid.UUID) -> CommercialOperation:
    op = db.scalar(select(CommercialOperation).where(CommercialOperation.id == op_id).with_for_update().execution_options(populate_existing=True))
    if op is None:
        raise ConnectionError("operation_not_found")
    require_case_access(op.case_id, actor, db)
    return op


def exchange(db: Session, actor: User, op_id: uuid.UUID, *, poll: bool = False) -> CommercialOperation:
    row = connection(db)
    op = owned_operation(db, actor, op_id)
    adapter = ADAPTERS.get(op.adapter)
    if not adapter:
        raise ConnectionError("unsupported_adapter")
    if (op.installation_id, op.tenant_id) != (row.installation_id, row.tenant_id):
        raise ConnectionError("operation_conflict")
    if op.state in {"completed", "failed", "applied"}:
        return op
    if (not poll and op.state != "pending") or (poll and op.state == "pending"):
        raise ConnectionError("reconciliation_required")
    secret, origin, version = decrypt_password(row.secret_enc), row.origin, row.version
    body = None
    if not poll:
        cred = db.get(CommercialCredential, op.credential_key, populate_existing=True)
        if not cred or not cred.secret_enc:
            raise ConnectionError("credential_required")
        op.credential_version = cred.version
        body = {"contract_version": VERSION, "installation_id": str(row.installation_id),
                "tenant_id": str(row.tenant_id), "operation_id": str(op.id),
                "fingerprint": op.fingerprint, "adapter": op.adapter,
                "payload": json.loads(decrypt_password(op.payload_enc)),
                "credential_version": cred.version, "credentials": json.loads(decrypt_password(cred.secret_enc))}
        # Crash or lost response from here onward requires reconciliation, never POST replay.
        op.state = "unknown"
        audit(db, actor, "dispatch_started", op.id)
    db.commit()
    failure = None
    try:
        data = Transport(origin).request("GET" if poll else "POST", "/v1/operations/" + str(op_id), body, secret)
    except ConnectionError as exc:
        data, failure = None, exc.code
    finally:
        body = None
        secret = None
    row = locked_connection(db)
    op = owned_operation(db, actor, op_id)
    if row.version != version or not row.secret_enc:
        raise ConnectionError("connection_changed")
    if op.state in {"completed", "failed", "applied"}:
        return op
    if failure:
        op.error_code = failure
    else:
        try:
            if data["contract_version"] != VERSION: raise ValueError()
            if data["installation_id"] != str(op.installation_id): raise ValueError()
            if data["tenant_id"] != str(op.tenant_id): raise ValueError()
            if data["operation_id"] != str(op.id) or data["fingerprint"] != op.fingerprint: raise ValueError()
            if set(data) - {"contract_version", "installation_id", "tenant_id", "operation_id", "fingerprint", "state", "result"}:
                raise ValueError()
            if data["state"] not in {"pending", "completed", "failed"}: raise ValueError()
            if data["state"] == "completed":
                result = adapter.validate_result(data["result"])
                reject_credentials(result)
                raw = encode(result)
                op.result_enc, op.result_hash = encrypt(raw), digest(raw)
            op.state = "submitted" if data["state"] == "pending" else data["state"]
            op.error_code = "provider_rejected" if op.state == "failed" else None
        except (KeyError, TypeError, ValueError, AssertionError, ConnectionError):
            op.error_code = "invalid_response"
    audit(db, actor, "reconciled" if poll else "dispatched", op.id)
    db.commit()
    return op


def apply_result(db: Session, actor: User, op_id: uuid.UUID) -> CommercialOperation:
    # Applying an already received result works while offline/disconnected.
    locked_connection(db)
    op = owned_operation(db, actor, op_id)
    receipt = db.get(CommercialApplication, op.id)
    if receipt:
        if receipt.result_hash != op.result_hash:
            raise ConnectionError("result_conflict")
        return op
    if op.state != "completed" or not op.result_enc:
        raise ConnectionError("result_not_ready")
    adapter = ADAPTERS.get(op.adapter)
    if not adapter:
        raise ConnectionError("unsupported_adapter")
    raw = decrypt_password(op.result_enc)
    if digest(raw) != op.result_hash:
        raise ConnectionError("result_conflict")
    result = adapter.validate_result(json.loads(raw))
    try:
        def forbid_commit(session):
            raise ConnectionError("adapter_commit_forbidden")
        transaction = db.get_transaction()
        event.listen(db, "before_commit", forbid_commit)
        try:
            adapter.apply(db, op, result)
        finally:
            event.remove(db, "before_commit", forbid_commit)
        if db.get_transaction() is not transaction or not transaction.is_active:
            raise ConnectionError("adapter_transaction_changed")
        db.add(CommercialApplication(operation_id=op.id, result_hash=op.result_hash))
        op.state = "applied"
        audit(db, actor, "applied", op.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return op

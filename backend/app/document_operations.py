"""Caller-scoped durable receipts; operation, audit and receipt commit together."""

import functools
import hashlib
import inspect
import json
import uuid
from fastapi import HTTPException
from app.deps import require_case_access
from app.models import File
from app.models.document_operation import DocumentOperation
from app.upload_receipts import lock_receipt


def _begin(kind, values):
    db, user, case_id = values["db"], values["user"], values["case_id"]
    require_case_access(case_id, user, db)
    if db.info.get("document_operation_active"):
        return db, None, None, None, True
    key = db.info.get("document_operation_key")
    identity = fingerprint = None
    if key:
        try:
            key = uuid.UUID(str(key))
        except ValueError:
            raise HTTPException(400, "Invalid document operation identity")
        identity = uuid.uuid5(
            uuid.NAMESPACE_URL, f"canary:document:{case_id}:{user.id}:{key}"
        )
        payload = {
            k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else str(v))
            for k, v in values.items()
            if k not in ("db", "user")
        }
        fingerprint = hashlib.sha256(
            json.dumps([kind, payload], sort_keys=True).encode()
        ).hexdigest()
        lock_receipt(db, identity)
        receipt = db.get(DocumentOperation, identity)
        if receipt:
            if receipt.fingerprint != fingerprint:
                raise HTTPException(
                    409, "This retry differs from the original document operation."
                )
            if kind.startswith("create"):
                row = db.get(
                    File,
                    uuid.UUID(
                        receipt.response.get("id") or receipt.response["file_id"]
                    ),
                )
                if row is None:
                    raise HTTPException(
                        410,
                        "The created document was deleted; retry will not recreate it.",
                    )
                from app.file_storage import FILES_ROOT
                from app.document_durability import safe_path

                path = safe_path(FILES_ROOT, row.storage_path)
                if row.case_id != case_id or not path.is_file():
                    raise HTTPException(
                        409,
                        "The created document needs recovery before confirming this retry.",
                    )
                with path.open("rb") as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                if row.checksum and checksum != row.checksum:
                    raise HTTPException(
                        409, "The created document failed its integrity check."
                    )
            return db, identity, fingerprint, dict(receipt.response), False
    db.info["document_operation_active"] = True
    return db, identity, fingerprint, None, False


def _finish(db, identity, fingerprint, result):
    if identity:
        response = (
            result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        )
        db.add(
            DocumentOperation(id=identity, fingerprint=fingerprint, response=response)
        )
    db.commit()
    return result


def document_operation(kind):
    def decorate(function):
        signature = inspect.signature(function)

        @functools.wraps(function)
        def execute(*args, **kwargs):
            db, identity, fingerprint, replay, nested = _begin(
                kind, signature.bind(*args, **kwargs).arguments
            )
            if replay is not None:
                return replay
            if nested:
                return function(*args, **kwargs)
            try:
                return _finish(db, identity, fingerprint, function(*args, **kwargs))
            except Exception:
                db.rollback()
                raise
            finally:
                db.info.pop("document_operation_active", None)

        @functools.wraps(function)
        async def execute_async(*args, **kwargs):
            db, identity, fingerprint, replay, nested = _begin(
                kind, signature.bind(*args, **kwargs).arguments
            )
            if replay is not None:
                return replay
            if nested:
                return await function(*args, **kwargs)
            try:
                return _finish(
                    db, identity, fingerprint, await function(*args, **kwargs)
                )
            except Exception:
                db.rollback()
                raise
            finally:
                db.info.pop("document_operation_active", None)

        wrapper = execute_async if inspect.iscoroutinefunction(function) else execute
        annotations = inspect.get_annotations(function, eval_str=True)
        wrapper.__signature__ = signature.replace(
            parameters=[
                p.replace(annotation=annotations.get(p.name, p.annotation))
                for p in signature.parameters.values()
            ],
            return_annotation=annotations.get("return", signature.return_annotation),
        )
        return wrapper

    return decorate

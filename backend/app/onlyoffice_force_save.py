"""ONLYOFFICE force-save helpers (arm / wait / CommandService)."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Literal

import httpx
import jwt as pyjwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import File as DbFile

log = logging.getLogger(__name__)

OoForceSavePhase = Literal["arm", "wait", "command", "command_wait"]


def oo_save_status(row, base_version, attempt_id=None):
    matches = attempt_id is not None and str(row.oo_save_attempt_id) == str(attempt_id)
    return {"saved": bool(matches and row.oo_save_state == "confirmed"
                           and row.oo_save_base_version == base_version),
            "version": row.version or 1,
            "state": row.oo_save_state if matches else "superseded"}


def oo_force_save_arm(db: Session, row: DbFile, doc_key: str = "") -> int:
    from app.document_durability import lock_document
    row = lock_document(db, row)
    base_version = row.version or 1
    row.oo_save_attempt_id = uuid.uuid4()
    row.oo_save_document_key = doc_key
    row.oo_save_base_version = base_version
    row.oo_save_state = "pending"
    row.oo_force_save_pending = True
    db.add(row)
    db.commit()
    return base_version


async def oo_force_save_wait(db: Session, row: DbFile, *, base_version: int,
                             timeout_loops: int = 60, attempt_id=None) -> None:
    # Never infer success from a version changed by another operation.
    for _ in range(timeout_loops):
        await asyncio.sleep(0.5)
        db.refresh(row)
        result = oo_save_status(row, base_version, attempt_id)
        if result["saved"]:
            return
        if result["state"] != "pending":
            break
    raise HTTPException(422, "The save was not confirmed in Canary storage. Keep the editor open and retry.")


async def oo_force_save_issue_command(
    db: Session,
    row: DbFile,
    *,
    doc_key: str,
    file_id: uuid.UUID,
    attempt_id: uuid.UUID | None = None,
) -> None:
    """Issue CommandService forcesave (caller polls ``oo-save-status`` or uses ``oo_force_save_wait``)."""
    if attempt_id is None:
        oo_force_save_arm(db, row, doc_key)
        attempt_id = row.oo_save_attempt_id
    if (row.oo_save_attempt_id != attempt_id or row.oo_save_document_key != doc_key
            or row.oo_save_state != "pending"):
        raise HTTPException(409, "This save attempt has been superseded. Retry saving.")

    secret = (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()
    oo_internal = (os.getenv("ONLYOFFICE_DS_INTERNAL_URL") or "http://onlyoffice").strip().rstrip("/")
    cmd_url = f"{oo_internal}/coauthoring/CommandService.ashx"

    cmd_body: dict = {"c": "forcesave", "key": doc_key, "userdata": str(attempt_id)}
    token_str = pyjwt.encode(cmd_body, secret, algorithm="HS256")
    if isinstance(token_str, bytes):
        token_str = token_str.decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(cmd_url, json={**cmd_body, "token": token_str})
            resp.raise_for_status()
            body = resp.json()
            try:
                cmd_err = int(body.get("error", 0))
            except (TypeError, ValueError):
                cmd_err = 0
            if cmd_err == 4:
                log.info(
                    "oo_force_save: CommandService error=4 (unchanged on DS) file=%s",
                    file_id,
                )
                from app.document_durability import lock_document
                row = lock_document(db, row)
                if row.oo_save_attempt_id == attempt_id and row.oo_save_state == "pending":
                    row.oo_save_state = "failed"
                    row.oo_force_save_pending = False
                    db.commit()
                return
            if cmd_err != 0:
                raise RuntimeError(f"CommandService error={body.get('error')}")
        log.info("oo_force_save: issued force-save for file %s doc_key=%s", file_id, doc_key)
    except Exception as exc:
        log.warning("oo_force_save: command service failed for file %s: %s", file_id, exc)
        from app.document_durability import lock_document
        row = lock_document(db, row)
        if row.oo_save_attempt_id == attempt_id and row.oo_force_save_pending:
            row.oo_save_state = "failed"
            row.oo_force_save_pending = False
            db.add(row)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Force-save command failed — is the ONLYOFFICE service running?",
        ) from exc


async def oo_force_save_command_service(
    db: Session,
    row: DbFile,
    *,
    doc_key: str,
    file_id: uuid.UUID,
    attempt_id: uuid.UUID | None = None,
) -> None:
    """Issue CommandService forcesave and block until callback (legacy)."""
    if attempt_id is None:
        oo_force_save_arm(db, row, doc_key)
        attempt_id = row.oo_save_attempt_id
    previous_version = row.oo_save_base_version
    await oo_force_save_issue_command(db, row, doc_key=doc_key, file_id=file_id, attempt_id=attempt_id)
    await oo_force_save_wait(db, row, base_version=previous_version, timeout_loops=40, attempt_id=attempt_id)

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


def oo_force_save_arm(db: Session, row: DbFile) -> int:
    """Mark a pending host save and return the file version the client must wait to exceed."""
    base_version = row.version or 1
    row.oo_force_save_pending = True
    db.add(row)
    db.commit()
    return base_version


async def oo_force_save_wait(
    db: Session,
    row: DbFile,
    *,
    base_version: int,
    timeout_loops: int = 60,
) -> None:
    """Wait until ONLYOFFICE callback bumps ``version`` past ``base_version``."""
    for _ in range(timeout_loops):
        await asyncio.sleep(0.5)
        db.refresh(row)
        if (row.version or 1) > base_version:
            if row.oo_force_save_pending:
                row.oo_force_save_pending = False
                db.add(row)
                db.commit()
            return
    db.refresh(row)
    row.oo_force_save_pending = False
    db.add(row)
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "ONLYOFFICE did not confirm the save to Canary storage. "
            "Use the toolbar Save button once, then try Save Changes again."
        ),
    )


async def oo_force_save_issue_command(
    db: Session,
    row: DbFile,
    *,
    doc_key: str,
    file_id: uuid.UUID,
) -> None:
    """Issue CommandService forcesave (caller polls ``oo-save-status`` or uses ``oo_force_save_wait``)."""
    if not row.oo_force_save_pending:
        row.oo_force_save_pending = True
        db.add(row)
        db.commit()

    secret = (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()
    oo_internal = (os.getenv("ONLYOFFICE_DS_INTERNAL_URL") or "http://onlyoffice").strip().rstrip("/")
    cmd_url = f"{oo_internal}/coauthoring/CommandService.ashx"

    cmd_body: dict = {"c": "forcesave", "key": doc_key}
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
                return
            if cmd_err != 0:
                raise RuntimeError(f"CommandService error={body.get('error')}")
        log.info("oo_force_save: issued force-save for file %s doc_key=%s", file_id, doc_key)
    except Exception as exc:
        log.warning("oo_force_save: command service failed for file %s: %s", file_id, exc)
        db.refresh(row)
        if row.oo_force_save_pending:
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
) -> None:
    """Issue CommandService forcesave and block until callback (legacy)."""
    previous_version = row.version or 1
    await oo_force_save_issue_command(db, row, doc_key=doc_key, file_id=file_id)
    await oo_force_save_wait(db, row, base_version=previous_version, timeout_loops=40)

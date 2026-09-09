#!/usr/bin/env python3
"""Live deployment checks for the security hardening fixes.

Run inside the backend container:
  python scripts/live_security_verify.py
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

import httpx
from fastapi import HTTPException
from jose import jwt
from sqlalchemy import select, text

from app.audit import _safe_meta_json, log_event
from app.db import SessionLocal
from app.deps import require_portal_client_write
from app.feature_flags import onlyoffice_callback_require_jwt
from app.file_storage import FILES_ROOT, assert_under_files_root, path_is_under_files_root
from app.ledger_service import post_transaction
from app.models import Case, Contact, ContactPortalAccess, User
from app.portal_service import portal_session_version, staff_portal_access_code
from app.routers.onlyoffice import _decode_callback_payload
from app.schemas import LedgerPostCreate
from app.security import (
    PortalSessionPayload,
    create_access_token,
    create_portal_session_token,
    decode_portal_session_token,
)
from app.totp_secrets import decrypt_totp_secret, encrypt_totp_secret
from app.upload_limits import content_disposition_for_mime, max_upload_bytes

BASE = os.getenv("PORTAL_SMOKE_BASE", "http://127.0.0.1:8000").rstrip("/")
CASE_NUMBER = os.getenv("CASE_NUMBER", "000002").strip().zfill(6)
CONTACT_EMAIL = os.getenv("PORTAL_SMOKE_EMAIL", "sam.thomas@example.com").strip().lower()


@dataclass
class Report:
    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")

    @property
    def ok(self) -> bool:
        return all(r[1] for r in self.results)


def _staff_token(db) -> str:
    user = db.execute(select(User).where(User.is_active.is_(True))).scalars().first()
    if user is None:
        raise RuntimeError("No active staff user")
    return create_access_token(
        user_id=str(user.id),
        role=user.role.value,
        auth_token_version=int(getattr(user, "auth_token_version", 0) or 0),
    )


def _portal_contact(db) -> tuple[Contact, ContactPortalAccess]:
    from sqlalchemy import func

    preferred = (
        db.execute(
            select(Contact, ContactPortalAccess)
            .join(ContactPortalAccess, ContactPortalAccess.contact_id == Contact.id)
            .where(func.lower(Contact.email) == CONTACT_EMAIL)
            .limit(1)
        )
        .first()
    )
    if preferred:
        contact, access = preferred
        if staff_portal_access_code(access):
            return contact, access

    rows = db.execute(
        select(Contact, ContactPortalAccess)
        .join(ContactPortalAccess, ContactPortalAccess.contact_id == Contact.id)
        .where(ContactPortalAccess.enabled.is_(True))
        .limit(50)
    ).all()
    for contact, access in rows:
        code = staff_portal_access_code(access)
        if code:
            return contact, access
    raise RuntimeError("No portal contact with decryptable access code")


def _case(db) -> Case | None:
    case = db.execute(select(Case).where(Case.case_number == CASE_NUMBER)).scalar_one_or_none()
    if case is not None:
        return case
    return db.execute(select(Case).limit(1)).scalar_one_or_none()


def main() -> int:
    report = Report()
    print(f"Live security verify against {BASE}")
    print()

    # --- in-process / config checks (running code path) ---
    print("Config & unit-in-process")
    report.add("ONLYOFFICE JWT required by default", onlyoffice_callback_require_jwt() is True)

    req = MagicMock()
    req.headers = {}
    try:
        _decode_callback_payload(req, {"status": 2, "key": "live-check"})
        report.add("unsigned ONLYOFFICE callback rejected", False, "accepted unsigned body")
    except HTTPException as exc:
        report.add("unsigned ONLYOFFICE callback rejected", exc.status_code == 401, f"status={exc.status_code}")

    secret = os.getenv("ONLYOFFICE_JWT_SECRET", "").strip()
    if secret:
        token = jwt.encode({"status": 2, "key": "signed-live"}, secret, algorithm="HS256")
        out = _decode_callback_payload(req, {"token": token})
        report.add("signed ONLYOFFICE callback accepted", out.get("key") == "signed-live")
    else:
        report.add("signed ONLYOFFICE callback accepted", False, "ONLYOFFICE_JWT_SECRET unset")

    raw = _safe_meta_json({"blob": "x" * 20_000, "keep": 1})
    report.add("audit meta truncation stays valid JSON", len(raw) <= 8000 and json.loads(raw).get("_truncated") is True)

    commits: list[str] = []

    class FakeDb:
        def add(self, _obj: Any) -> None:
            pass

        def flush(self) -> None:
            pass

        def commit(self) -> None:
            commits.append("commit")

    log_event(FakeDb(), actor_user_id=None, action="live.security.probe", meta={"a": 1})
    report.add("log_event does not commit", commits == [])

    plain = "JBSWY3DPEHPK3PXP"
    enc = encrypt_totp_secret(plain)
    report.add("TOTP encrypt/decrypt roundtrip", enc != plain and decrypt_totp_secret(enc) == plain)
    report.add("legacy plaintext TOTP still readable", decrypt_totp_secret(plain) == plain)

    report.add("safe inline MIME for PDF", content_disposition_for_mime("application/pdf", download=False) == "inline")
    report.add("unsafe MIME forces attachment", content_disposition_for_mime("application/zip", download=False) == "attachment")
    report.add("upload max bytes configured", max_upload_bytes() >= 1024)

    try:
        assert_under_files_root(FILES_ROOT / "cases" / "x")
        report.add("path under FILES_ROOT accepted", True)
    except Exception as exc:
        report.add("path under FILES_ROOT accepted", False, str(exc))

    evil = Path(str(FILES_ROOT) + "_evil") / "x"
    report.add("FILES_ROOT string-prefix escape rejected", path_is_under_files_root(evil) is False)

    try:
        require_portal_client_write(PortalSessionPayload(contact_id=str(uuid.uuid4()), staff_preview=True))
        report.add("preview write guard raises", False, "no raise")
    except HTTPException as exc:
        report.add("preview write guard raises", exc.status_code == 403, f"status={exc.status_code}")

    # --- DB-backed ledger deficit ---
    print()
    print("Ledger (live DB)")
    db = SessionLocal()
    try:
        case = _case(db)
        admin = db.execute(select(User).where(User.is_active.is_(True))).scalars().first()
        if case is None or admin is None:
            report.add("ledger deficit rejected on live DB", False, "missing case/user")
        else:
            try:
                post_transaction(
                    case.id,
                    LedgerPostCreate(
                        description="live security deficit probe",
                        amount_pence=10**12,
                        client_direction="debit",
                    ),
                    admin,
                    db,
                )
                db.rollback()
                report.add("ledger deficit rejected on live DB", False, "post accepted")
            except HTTPException as exc:
                db.rollback()
                report.add("ledger deficit rejected on live DB", exc.status_code == 422, f"status={exc.status_code}")

        # session_version column present
        cols = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='contact_portal_access' AND column_name='session_version'"
            )
        ).scalar_one_or_none()
        report.add("portal session_version column present", cols == "session_version")

        # stale portal session rejected
        contact, access = _portal_contact(db)
        stale = create_portal_session_token(
            contact_id=str(contact.id),
            session_version=int(portal_session_version(access)) + 99,
        )
        payload = decode_portal_session_token(stale)
        report.add(
            "stale session_version encoded in JWT",
            payload.session_version == int(portal_session_version(access)) + 99,
            f"contact={contact.email or contact.id}",
        )
    except Exception as exc:
        db.rollback()
        report.add("ledger/session DB checks", False, f"{exc}\n{traceback.format_exc()[:400]}")
    finally:
        db.close()

    # --- HTTP against live API ---
    print()
    print("HTTP against live API")
    db = SessionLocal()
    try:
        staff = _staff_token(db)
        contact, access = _portal_contact(db)
        code = staff_portal_access_code(access)
        assert code
        with httpx.Client(base_url=BASE, timeout=30.0) as client:
            # health
            h = client.get("/health")
            report.add("GET /health", h.status_code == 200, h.text[:80])

            # portal auth
            auth = client.post("/portal/auth", json={"access_code": code})
            report.add("portal auth with access code", auth.status_code == 200, auth.text[:120])
            sess = auth.json().get("session_token") if auth.status_code == 200 else None

            # stale session version rejected by API
            stale_tok = create_portal_session_token(
                contact_id=str(contact.id),
                session_version=int(portal_session_version(access)) + 50,
            )
            stale_r = client.get("/portal/session", headers={"Authorization": f"Bearer {stale_tok}"})
            report.add("API rejects stale portal session_version", stale_r.status_code == 401, stale_r.text[:120])

            if sess:
                good = client.get("/portal/session", headers={"Authorization": f"Bearer {sess}"})
                report.add("API accepts current portal session", good.status_code == 200, good.text[:120])

            # staff preview exchange + write block on upload if we can get preview
            case = _case(db)
            if case is None:
                report.add("preview write HTTP block", False, f"case {CASE_NUMBER} missing")
            else:
                prev = client.post(
                    f"/cases/{case.id}/portal/preview",
                    headers={"Authorization": f"Bearer {staff}"},
                    json={"contact_id": str(contact.id)},
                )
                if prev.status_code != 200:
                    report.add("staff portal preview mint", False, prev.text[:160])
                else:
                    exchange = client.post(
                        "/portal/auth/preview-exchange",
                        json={"exchange_token": prev.json()["exchange_token"]},
                    )
                    report.add("preview-exchange", exchange.status_code == 200, exchange.text[:120])
                    ptok = exchange.json().get("session_token") if exchange.status_code == 200 else None
                    if ptok:
                        # upload should 403 in preview
                        files = {
                            "upload": ("probe.txt", BytesIO(b"live-security-probe"), "text/plain"),
                        }
                        # need a grant id — list session grants
                        sess_info = client.get("/portal/session", headers={"Authorization": f"Bearer {ptok}"})
                        grants = (sess_info.json() or {}).get("grants") or []
                        if not grants:
                            report.add("preview upload blocked", False, "no grants on preview session")
                        else:
                            gid = grants[0]["id"]
                            up = client.post(
                                f"/portal/grants/{gid}/files",
                                headers={"Authorization": f"Bearer {ptok}"},
                                files=files,
                                data={"folder": grants[0].get("folder_path") or ""},
                            )
                            report.add(
                                "preview upload blocked (write guard)",
                                up.status_code == 403,
                                up.text[:160],
                            )

            # oversized portal upload rejected for real session (if we have grant)
            if sess:
                sess_info = client.get("/portal/session", headers={"Authorization": f"Bearer {sess}"})
                grants = (sess_info.json() or {}).get("grants") or []
                if grants:
                    gid = grants[0]["id"]
                    # Just over the configured max
                    big = BytesIO(b"0" * (max_upload_bytes() + 1024))
                    up = client.post(
                        f"/portal/grants/{gid}/files",
                        headers={"Authorization": f"Bearer {sess}"},
                        files={"upload": ("too-big.bin", big, "application/octet-stream")},
                        data={"folder": grants[0].get("folder_path") or ""},
                    )
                    report.add(
                        "oversized portal upload rejected",
                        up.status_code in {413, 400, 422},
                        f"status={up.status_code} {up.text[:120]}",
                    )
                else:
                    report.add("oversized portal upload rejected", False, "no grants for contact")
    except Exception as exc:
        report.add("HTTP live checks", False, f"{exc}\n{traceback.format_exc()[:500]}")
    finally:
        db.close()

    print()
    passed = sum(1 for _, ok, _ in report.results if ok)
    total = len(report.results)
    print(f"Result: {passed}/{total} passed")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

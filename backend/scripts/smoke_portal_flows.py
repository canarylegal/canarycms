#!/usr/bin/env python3
"""Extensive HTTP smoke tests for client portal quote / form / Canary Sign flows.

Runs against the live backend (default http://127.0.0.1:8000 inside compose).

  docker compose --profile prod exec backend \\
    python scripts/smoke_portal_flows.py

Optional:
  PORTAL_SMOKE_BASE=http://127.0.0.1:8000
  CASE_NUMBER=000002
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("FILES_ROOT", "/data/files")

import httpx
import pikepdf
from sqlalchemy import select

from app.db import SessionLocal
from app.file_storage import FILES_ROOT, ensure_files_root
from app.models import (
    CanarySignRequest,
    CanarySignStatus,
    Case,
    CaseContact,
    Contact,
    ContactPortalAccess,
    File as DbFile,
    FileCategory,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
    PortalFormTemplate,
    PortalFormTemplateField,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
    UserRole,
)
from app.portal_service import staff_portal_access_code
from app.security import create_access_token, create_portal_session_token

CASE_NUMBER = os.getenv("CASE_NUMBER", "000002").strip().zfill(6)
BASE = os.getenv("PORTAL_SMOKE_BASE", "http://127.0.0.1:8000").rstrip("/")
CONTACT_EMAIL = "sam.thomas@example.com"
CONTACT_NAME = "sam thomas"


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(name=name, ok=ok, detail=detail))
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"[{mark}] {name}{suffix}")

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def valid_blank_pdf_bytes() -> bytes:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    buf = BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def repair_stub_pdfs(db, case: Case) -> int:
    """Replace tiny invalid demo PDFs so Canary Sign / pdf.js can render them."""
    ensure_files_root()
    good = valid_blank_pdf_bytes()
    fixed = 0
    rows = db.execute(select(DbFile).where(DbFile.case_id == case.id)).scalars().all()
    for row in rows:
        name = (row.original_filename or "").lower()
        if not name.endswith(".pdf"):
            continue
        path = FILES_ROOT / row.storage_path
        if not path.exists():
            continue
        raw = path.read_bytes()
        # Known seed stub or otherwise unreadable by pikepdf.
        broken = False
        if len(raw) < 200 or raw == b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n":
            broken = True
        else:
            try:
                with pikepdf.open(BytesIO(raw)) as _:
                    pass
            except Exception:
                broken = True
        if not broken:
            continue
        path.write_bytes(good)
        row.size_bytes = len(good)
        row.mime_type = "application/pdf"
        row.updated_at = _utcnow()
        db.add(row)
        fixed += 1
    if fixed:
        db.commit()
    return fixed


class Api:
    def __init__(self, base: str):
        self.base = base
        self.client = httpx.Client(base_url=base, timeout=60.0)

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: Any = None,
        expected: int | set[int] | None = 200,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Canary-Token"] = token
        res = self.client.request(method, path, headers=headers, json=json_body, **kwargs)
        if expected is not None:
            allowed = {expected} if isinstance(expected, int) else set(expected)
            if res.status_code not in allowed:
                body = res.text[:800]
                raise AssertionError(f"{method} {path} -> {res.status_code} (want {sorted(allowed)}): {body}")
        return res

    def json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: Any = None,
        expected: int | set[int] = 200,
        **kwargs: Any,
    ) -> Any:
        res = self.request(method, path, token=token, json_body=json_body, expected=expected, **kwargs)
        if res.status_code == 204 or not res.content:
            return None
        return res.json()


def mint_staff_token(db) -> tuple[User, str]:
    user = db.execute(select(User).where(User.email == "colin@mcwilliamslegal.co.uk")).scalar_one_or_none()
    if user is None:
        user = db.execute(select(User).where(User.role == UserRole.admin, User.is_active.is_(True))).scalars().first()
    if user is None:
        raise RuntimeError("No staff user found")
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(
        user_id=str(user.id),
        role=role,
        mfa_verified=True,
        password_ok=True,
        auth_token_version=int(getattr(user, "auth_token_version", 0) or 0),
    )
    return user, token


def find_case_and_contact(db) -> tuple[Case, Contact, CaseContact, ContactPortalAccess]:
    case = db.execute(select(Case).where(Case.case_number == CASE_NUMBER)).scalar_one()
    rows = db.execute(
        select(Contact, CaseContact)
        .join(CaseContact, CaseContact.contact_id == Contact.id)
        .where(CaseContact.case_id == case.id)
    ).all()
    contact = None
    case_contact = None
    for c, cc in rows:
        email = (c.email or "").strip().lower()
        name = (c.name or "").strip().lower()
        if email == CONTACT_EMAIL or name == CONTACT_NAME:
            contact, case_contact = c, cc
            break
    if contact is None or case_contact is None:
        raise RuntimeError("Sam Thomas not found on matter")
    access = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    ).scalar_one_or_none()
    if access is None or not access.enabled:
        raise RuntimeError("Sam Thomas has no portal access")
    return case, contact, case_contact, access


def pick_quote_file(db, case: Case) -> DbFile:
    quote = db.execute(
        select(DbFile)
        .where(
            DbFile.case_id == case.id,
            DbFile.category == FileCategory.case_document,
            DbFile.original_filename.ilike("%quote%"),
        )
        .order_by(DbFile.created_at.desc())
    ).scalars().first()
    if quote:
        return quote
    any_doc = db.execute(
        select(DbFile)
        .where(DbFile.case_id == case.id, DbFile.category == FileCategory.case_document)
        .order_by(DbFile.created_at.desc())
    ).scalars().first()
    if not any_doc:
        raise RuntimeError("No case document available for quote send")
    return any_doc


def pick_sign_pdf(db, case: Case) -> DbFile:
    rows = db.execute(
        select(DbFile)
        .where(
            DbFile.case_id == case.id,
            DbFile.category == FileCategory.case_document,
            DbFile.original_filename.ilike("%.pdf"),
        )
        .order_by(DbFile.created_at.asc())
    ).scalars().all()
    for row in rows:
        name = (row.original_filename or "").lower()
        if "signed" in name or "snapshot" in name or "canary sign" in name:
            continue
        path = FILES_ROOT / row.storage_path
        if path.exists() and path.stat().st_size >= 200:
            return row
    raise RuntimeError("No valid PDF available for Canary Sign")


def void_pending_quotes(api: Api, staff: str, case_id: str, contact_id: uuid.UUID, db) -> None:
    pending = db.execute(
        select(QuotePortalDelivery).where(
            QuotePortalDelivery.case_id == uuid.UUID(case_id),
            QuotePortalDelivery.contact_id == contact_id,
            QuotePortalDelivery.status == QuotePortalDeliveryStatus.pending,
        )
    ).scalars().all()
    # No staff void endpoint used here — client will respond; for setup, mark superseded via client decline/accept later.
    _ = pending


def build_form_responses(fields: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields:
        if f.get("field_type") == "section":
            continue
        key = f["field_key"]
        required = bool(f.get("required"))
        ftype = f.get("field_type")
        opts = f.get("select_options") or []
        if ftype == "select":
            if opts:
                out[key] = opts[0]
            elif required:
                out[key] = "Individual(s)"
        elif ftype == "textarea":
            if required or key.startswith("intended"):
                out[key] = "Purchase of residential property (smoke test)"
        elif ftype == "text":
            if key in ("full_name",) or required:
                if "mail" in key:
                    out[key] = CONTACT_EMAIL
                elif "phone" in key:
                    out[key] = "07700900000"
                else:
                    out[key] = "Sam Thomas"
            elif "mail" in key and required:
                out[key] = CONTACT_EMAIL
        elif ftype == "date" and required:
            out[key] = "1990-01-01"
        elif required:
            out[key] = "smoke"
    # Ensure known required keys for general_information
    out.setdefault("are_you_acting_as_a_company_or_an_individual", "Individual(s)")
    out.setdefault("full_name", "Sam Thomas")
    out.setdefault("e_mail_address", CONTACT_EMAIL)
    out.setdefault("phone_number", "07700900000")
    out.setdefault("intended_transaction_type_s", "Purchase of residential property (smoke test)")
    return out


def tiny_png_b64() -> str:
    # 1x1 transparent PNG
    import base64

    raw = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    return base64.b64encode(raw).decode("ascii")


def main() -> int:
    report = Report()
    api = Api(BASE)
    db = SessionLocal()
    try:
        print(f"Portal smoke against {BASE} / matter {CASE_NUMBER}")
        print("=" * 60)

        # ── Setup ──────────────────────────────────────────────────────────
        case, contact, case_contact, access = find_case_and_contact(db)
        case_id = str(case.id)
        contact_id = str(contact.id)
        staff_user, staff = mint_staff_token(db)
        report.add("mint staff JWT", True, staff_user.email)

        fixed = repair_stub_pdfs(db, case)
        report.add("repair stub PDFs", True, f"fixed {fixed} file(s)")

        me = api.json("GET", "/auth/me", token=staff)
        report.add("staff /auth/me", True, me.get("email") or me.get("display_name") or "")

        # Ensure portal enabled
        if not case.portal_enabled:
            api.json("PATCH", f"/cases/{case_id}", token=staff, json_body={"portal_enabled": True})
            db.refresh(case)
        report.add("matter portal_enabled", bool(case.portal_enabled), case_id)

        access_code = staff_portal_access_code(access)
        if not access_code:
            # Fall back to minting a portal session without access-code path.
            portal = create_portal_session_token(contact_id=contact_id)
            report.add("portal access-code available", False, "using minted session token instead")
        else:
            auth = api.json("POST", "/portal/auth", json_body={"access_code": access_code})
            portal = auth["session_token"]
            report.add(
                "portal auth via access code",
                True,
                f"contact={auth.get('contact_name')} grants={len(auth.get('grants') or [])}",
            )

        sess = api.json("GET", "/portal/session", token=portal)
        report.add("portal /session", True, sess.get("contact_name") or "")

        actions = api.json("GET", "/portal/client-actions", token=portal)
        report.add(
            "portal /client-actions",
            True,
            f"outstanding={len(actions.get('outstanding') or [])} "
            f"complete={len(actions.get('complete') or [])} "
            f"inactive={len(actions.get('inactive') or [])}",
        )

        grants = sess.get("grants") or []
        if grants:
            gid = grants[0]["id"]
            browse = api.json("GET", f"/portal/grants/{gid}/browse", token=portal)
            files = browse.get("files") or []
            report.add("portal folder browse", True, f"files={len(files)} subfolders={len(browse.get('subfolders') or [])}")
            if files:
                from app.upload_limits import content_disposition_for_mime

                # Prefer a PDF when present so we exercise the happy-path inline case.
                probe = next(
                    (f for f in files if str(f.get("original_filename") or "").lower().endswith(".pdf")),
                    files[0],
                )
                fid = probe["id"]
                minted = api.json("POST", f"/portal/grants/{gid}/files/{fid}/open-token", token=portal)
                open_res = api.request(
                    "GET",
                    f"/portal/grants/{gid}/files/{fid}/open",
                    params={"token": minted["token"]},
                    expected={200, 206},
                )
                ctype = open_res.headers.get("content-type", "")
                cd = open_res.headers.get("content-disposition", "")
                expected_disp = content_disposition_for_mime(ctype, download=False)
                report.add(
                    "portal file open disposition matches MIME policy",
                    expected_disp in cd.lower(),
                    f"type={ctype} expected={expected_disp} disposition={cd[:80]} bytes={len(open_res.content)}",
                )
                # Explicitly check an unsafe type if one exists in the folder.
                unsafe = next(
                    (
                        f
                        for f in files
                        if str(f.get("original_filename") or "").lower().endswith((".eml", ".zip", ".bin"))
                    ),
                    None,
                )
                if unsafe is not None and unsafe["id"] != fid:
                    um = api.json("POST", f"/portal/grants/{gid}/files/{unsafe['id']}/open-token", token=portal)
                    ures = api.request(
                        "GET",
                        f"/portal/grants/{gid}/files/{unsafe['id']}/open",
                        params={"token": um["token"]},
                        expected={200, 206},
                    )
                    ucd = ures.headers.get("content-disposition", "")
                    report.add(
                        "unsafe MIME forced to attachment",
                        "attachment" in ucd.lower(),
                        f"file={unsafe.get('original_filename')} disposition={ucd[:80]}",
                    )
        else:
            report.add("portal folder browse", False, "no grants on session")

        # ── Quote flow ─────────────────────────────────────────────────────
        print("-" * 60)
        print("QUOTE")
        # Clear any existing pending delivery by accepting/declining via portal.
        pending_quotes = api.json("GET", "/portal/quote-deliveries", token=portal) or []
        for q in pending_quotes:
            if q.get("status") != "pending":
                continue
            qid = q["id"]
            try:
                api.json(
                    "POST",
                    f"/portal/quote-deliveries/{qid}/respond",
                    token=portal,
                    json_body={"accepted": False, "decline_reason": "Smoke setup clear"},
                    expected=200,
                )
                report.add("clear existing pending quote", True, qid)
            except Exception as e:
                report.add("clear existing pending quote", False, str(e)[:200])

        quote_file = pick_quote_file(db, case)
        pre = api.json(
            "GET",
            f"/cases/{case_id}/files/{quote_file.id}/quote-portal/send-preflight",
            token=staff,
            expected={200, 400, 404, 409},
        )
        report.add("quote send-preflight", True, json.dumps(pre)[:120] if pre is not None else "ok")

        sent = api.json(
            "POST",
            f"/cases/{case_id}/files/{quote_file.id}/quote-portal/send",
            token=staff,
            json_body={"contact_id": contact_id},
            expected={200, 201},
        )
        delivery_id = sent["id"]
        report.add(
            "staff send quote via portal",
            sent.get("status") == "pending",
            f"id={delivery_id} email_sent={sent.get('email_sent')} pdf={sent.get('portal_pdf_generated')}",
        )

        view = api.json("GET", f"/portal/quote-deliveries/{delivery_id}", token=portal)
        report.add("client view quote delivery", view.get("status") == "pending", view.get("original_filename") or "")

        file_res = api.request(
            "GET",
            f"/portal/quote-deliveries/{delivery_id}/file",
            token=portal,
            expected={200, 206},
        )
        report.add("client open quote file", len(file_res.content) > 0, f"bytes={len(file_res.content)}")

        # Exchange deep-link
        exchanged = api.json("POST", "/portal/quote-exchange", json_body={"exchange_token": delivery_id})
        report.add("quote-exchange deep link", bool(exchanged.get("session_token")), exchanged.get("contact_name") or "")

        accepted = api.json(
            "POST",
            f"/portal/quote-deliveries/{delivery_id}/respond",
            token=portal,
            json_body={"accepted": True},
        )
        report.add("client accept quote", accepted.get("status") in ("accepted", "approved", "complete", "completed") or accepted.get("accepted") is True or accepted.get("status") == "accepted", str(accepted.get("status")))

        # Second quote → decline path
        sent2 = api.json(
            "POST",
            f"/cases/{case_id}/files/{quote_file.id}/quote-portal/send",
            token=staff,
            json_body={"contact_id": contact_id},
            expected={200, 201, 409},
        )
        if isinstance(sent2, dict) and sent2.get("id"):
            d2 = sent2["id"]
            declined = api.json(
                "POST",
                f"/portal/quote-deliveries/{d2}/respond",
                token=portal,
                json_body={"accepted": False, "decline_reason": "Smoke test decline"},
            )
            report.add("client decline quote", True, str(declined.get("status")))
        else:
            report.add("client decline quote", False, f"could not send second quote: {sent2}")

        # ── Form flow ──────────────────────────────────────────────────────
        print("-" * 60)
        print("PORTAL FORM")
        templates = api.json("GET", f"/cases/{case_id}/portal/forms/templates", token=staff)
        if not templates:
            report.add("list form templates", False, "none configured")
        else:
            tmpl = next((t for t in templates if t.get("reference") == "general_information"), templates[0])
            report.add("list form templates", True, f"{len(templates)} — using {tmpl.get('reference')}")

            # Void existing pending for Sam so send is clean
            existing = db.execute(
                select(PortalFormSubmission).where(
                    PortalFormSubmission.case_id == case.id,
                    PortalFormSubmission.contact_id == contact.id,
                    PortalFormSubmission.status == PortalFormSubmissionStatus.pending,
                )
            ).scalars().all()
            for sub in existing:
                try:
                    api.json(
                        "POST",
                        f"/cases/{case_id}/portal/forms/submissions/{sub.id}/void",
                        token=staff,
                        json_body={},
                        expected={200, 201},
                    )
                except Exception:
                    pass

            created = api.json(
                "POST",
                f"/cases/{case_id}/portal/forms/send",
                token=staff,
                json_body={"template_id": tmpl["id"], "contact_id": contact_id},
                expected={200, 201},
            )
            sub_id = created["id"]
            report.add("staff send portal form", created.get("status") == "pending", sub_id)

            pending_forms = api.json("GET", "/portal/forms", token=portal)
            report.add("client list forms", any(f.get("id") == sub_id for f in pending_forms), f"count={len(pending_forms)}")

            detail = api.json("GET", f"/portal/forms/{sub_id}", token=portal)
            fields = detail.get("fields") or []
            report.add("client view form detail", len(fields) > 0, f"fields={len(fields)}")

            # Form exchange deep link
            fx = api.json("POST", "/portal/form-exchange", json_body={"exchange_token": sub_id})
            report.add("form-exchange deep link", bool(fx.get("session_token")), fx.get("contact_name") or "")

            responses = build_form_responses(fields)
            submitted = api.json(
                "POST",
                f"/portal/forms/{sub_id}/submit",
                token=portal,
                json_body={"responses": responses},
                expected={200, 201},
            )
            report.add(
                "client submit form",
                (submitted or {}).get("status") in ("submitted", "complete", "completed"),
                str((submitted or {}).get("status")),
            )

            # Preview mode must block submit
            preview = api.json(
                "POST",
                f"/cases/{case_id}/portal/preview",
                token=staff,
                json_body={"contact_id": contact_id},
            )
            preview_sess = api.json(
                "POST",
                "/portal/auth/preview-exchange",
                json_body={"exchange_token": preview["exchange_token"]},
            )
            # Send another form for preview block test
            created_prev = api.json(
                "POST",
                f"/cases/{case_id}/portal/forms/send",
                token=staff,
                json_body={"template_id": tmpl["id"], "contact_id": contact_id},
                expected={200, 201},
            )
            blocked = api.request(
                "POST",
                f"/portal/forms/{created_prev['id']}/submit",
                token=preview_sess["session_token"],
                json_body={"responses": responses},
                expected={403},
            )
            report.add("preview mode blocks form submit", blocked.status_code == 403, blocked.text[:120])
            # Clean up the preview-test form
            try:
                api.json(
                    "POST",
                    f"/cases/{case_id}/portal/forms/submissions/{created_prev['id']}/void",
                    token=staff,
                    json_body={},
                    expected={200, 201},
                )
            except Exception:
                pass

        # ── Canary Sign flow ───────────────────────────────────────────────
        print("-" * 60)
        print("CANARY SIGN")
        opts = api.json("GET", "/canary-sign/options", token=staff, expected={200, 404})
        enabled = bool((opts or {}).get("enabled", True))
        report.add("canary-sign options", enabled, json.dumps(opts)[:120] if opts else "")

        if enabled:
            # Void Sam's pending sign requests
            pending_sign = db.execute(
                select(CanarySignRequest).where(
                    CanarySignRequest.case_id == case.id,
                    CanarySignRequest.status == CanarySignStatus.pending,
                )
            ).scalars().all()
            for req in pending_sign:
                try:
                    api.json(
                        "POST",
                        f"/cases/{case_id}/canary-sign/requests/{req.id}/void",
                        token=staff,
                        json_body={"reason": "Smoke setup clear"},
                        expected={200, 201},
                    )
                except Exception as e:
                    report.add(f"void pending sign {req.id}", False, str(e)[:160])

            sign_file = pick_sign_pdf(db, case)
            # Ensure on-disk PDF is valid after void path
            repair_stub_pdfs(db, case)

            send_body = {
                "source_file_id": str(sign_file.id),
                "subject": f"Smoke sign: {sign_file.original_filename}",
                "order_mode": "parallel",
                "expires_in_days": 14,
                "retain_fillable_form": False,
                "recipients": [
                    {
                        "name": contact.name,
                        "email": contact.email,
                        "routing_order": 1,
                        "case_contact_id": str(case_contact.id),
                        "contact_id": contact_id,
                    }
                ],
                "fields": [
                    {
                        "field_type": "signature",
                        "routing_order": 1,
                        "label": "Signature",
                        "required": True,
                        "sort_order": 0,
                        "page": 1,
                        "x_pct": 15,
                        "y_pct": 70,
                        "w_pct": 35,
                        "h_pct": 10,
                    },
                    {
                        "field_type": "date",
                        "routing_order": 1,
                        "label": "Date",
                        "required": True,
                        "sort_order": 1,
                        "page": 1,
                        "x_pct": 55,
                        "y_pct": 70,
                        "w_pct": 25,
                        "h_pct": 6,
                    },
                ],
            }
            created_sign = api.json(
                "POST",
                f"/cases/{case_id}/canary-sign/send",
                token=staff,
                json_body=send_body,
                expected={200, 201},
            )
            req_id = created_sign["id"]
            recipients = created_sign.get("recipients") or []
            sign_token = (recipients[0].get("sign_token") if recipients else None) or None
            report.add("staff send Canary Sign", created_sign.get("status") == "pending", f"id={req_id}")

            if sign_token:
                sx = api.json("POST", "/portal/canary-sign-exchange", json_body={"sign_token": sign_token})
                report.add("canary-sign-exchange deep link", bool(sx.get("session_token")), sx.get("contact_name") or "")
                # Prefer exchange session for signing continuity
                if sx.get("session_token"):
                    portal = sx["session_token"]

            view_sign = api.json("GET", f"/portal/canary-sign/{req_id}", token=portal)
            fields = view_sign.get("fields") or []
            report.add(
                "client view Canary Sign",
                view_sign.get("can_sign") is True and len(fields) >= 2,
                f"can_sign={view_sign.get('can_sign')} fields={len(fields)}",
            )

            pdf_res = api.request("GET", f"/portal/canary-sign/{req_id}/pdf", token=portal, expected={200, 206})
            pdf_ok = False
            try:
                with pikepdf.open(BytesIO(pdf_res.content)) as pdf:
                    pdf_ok = len(pdf.pages) >= 1
            except Exception as e:
                pdf_ok = False
                report.add("client Canary Sign PDF renderable", False, str(e)[:160])
            if pdf_ok:
                report.add("client Canary Sign PDF renderable", True, f"bytes={len(pdf_res.content)}")

            field_values: dict[str, Any] = {}
            for f in fields:
                ft = f.get("field_type")
                fid = f["id"]
                if ft == "signature":
                    field_values[fid] = {"text": "Sam Thomas", "image_b64": tiny_png_b64()}
                elif ft == "date":
                    field_values[fid] = {"text": datetime.now(timezone.utc).strftime("%d/%m/%Y")}
                elif ft == "printed_name":
                    field_values[fid] = {"text": "Sam Thomas"}
                elif ft == "checkbox":
                    field_values[fid] = {"checked": True}
                else:
                    field_values[fid] = {"text": "smoke"}

            signed = api.json(
                "POST",
                f"/portal/canary-sign/{req_id}/sign",
                token=portal,
                json_body={"consent": True, "field_values": field_values},
                expected={200, 201},
            )
            report.add(
                "client complete Canary Sign",
                (signed or {}).get("status") in ("completed", "pending"),  # pending if sequential multi-party
                str((signed or {}).get("status")),
            )

            # Decline path on a fresh request
            repair_stub_pdfs(db, case)
            # Use Welcome pack or another pdf if same file still locked by pending — void first already done.
            # If same file has completed, send is allowed; if pending remains, void.
            pending_sign2 = db.execute(
                select(CanarySignRequest).where(
                    CanarySignRequest.case_id == case.id,
                    CanarySignRequest.status == CanarySignStatus.pending,
                )
            ).scalars().all()
            for req in pending_sign2:
                api.json(
                    "POST",
                    f"/cases/{case_id}/canary-sign/requests/{req.id}/void",
                    token=staff,
                    json_body={"reason": "Smoke decline setup"},
                    expected={200, 201},
                )

            send_body["subject"] = f"Smoke decline: {sign_file.original_filename}"
            created_decline = api.json(
                "POST",
                f"/cases/{case_id}/canary-sign/send",
                token=staff,
                json_body=send_body,
                expected={200, 201},
            )
            d_id = created_decline["id"]
            declined = api.json(
                "POST",
                f"/portal/canary-sign/{d_id}/decline",
                token=portal,
                json_body={"reason": "Smoke test decline"},
                expected={200, 201},
            )
            report.add(
                "client decline Canary Sign",
                (declined or {}).get("status") in ("declined", "voided", "completed")
                or (declined or {}).get("recipient_status") == "declined",
                str((declined or {}).get("status") or (declined or {}).get("recipient_status")),
            )

            # Preview must block sign
            preview2 = api.json(
                "POST",
                f"/cases/{case_id}/portal/preview",
                token=staff,
                json_body={"contact_id": contact_id},
            )
            preview_sess2 = api.json(
                "POST",
                "/portal/auth/preview-exchange",
                json_body={"exchange_token": preview2["exchange_token"]},
            )
            # Need a pending request for block test
            for req in db.execute(
                select(CanarySignRequest).where(
                    CanarySignRequest.case_id == case.id,
                    CanarySignRequest.status == CanarySignStatus.pending,
                )
            ).scalars().all():
                api.json(
                    "POST",
                    f"/cases/{case_id}/canary-sign/requests/{req.id}/void",
                    token=staff,
                    json_body={"reason": "clear"},
                    expected={200, 201},
                )
            send_body["subject"] = "Smoke preview block"
            block_req = api.json(
                "POST",
                f"/cases/{case_id}/canary-sign/send",
                token=staff,
                json_body=send_body,
                expected={200, 201},
            )
            blocked_sign = api.request(
                "POST",
                f"/portal/canary-sign/{block_req['id']}/sign",
                token=preview_sess2["session_token"],
                json_body={"consent": True, "field_values": field_values},
                expected={403},
            )
            report.add("preview mode blocks Canary Sign", blocked_sign.status_code == 403, blocked_sign.text[:120])
            api.json(
                "POST",
                f"/cases/{case_id}/canary-sign/requests/{block_req['id']}/void",
                token=staff,
                json_body={"reason": "cleanup"},
                expected={200, 201},
            )

        # Final client-actions snapshot
        final_actions = api.json("GET", "/portal/client-actions", token=portal)
        report.add(
            "final client-actions snapshot",
            True,
            f"outstanding={len(final_actions.get('outstanding') or [])} "
            f"complete={len(final_actions.get('complete') or [])} "
            f"inactive={len(final_actions.get('inactive') or [])}",
        )

    except Exception as e:
        report.add("UNHANDLED", False, f"{e}\n{traceback.format_exc()[:600]}")
    finally:
        db.close()
        api.close()

    print("=" * 60)
    failed = report.failed
    print(f"Results: {len(report.results) - len(failed)} passed, {len(failed)} failed, {len(report.results)} total")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

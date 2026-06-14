"""Client portal: access codes, grants, and folder scope checks."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.file_storage import sanitize_folder_path
from app.models import Case, Contact, ContactPortalAccess, ContactPortalGrant, File, FileCategory, PortalLoginOtp

PORTAL_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PORTAL_CODE_GROUPS = (4, 4, 4)
PORTAL_MAX_FAILED_ATTEMPTS = 5
PORTAL_LOCKOUT_MINUTES = 15


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_access_code(raw: str) -> str:
    return "".join(ch for ch in (raw or "").upper() if ch.isalnum())


def format_access_code(raw: str) -> str:
    n = normalize_access_code(raw)
    parts: list[str] = []
    i = 0
    for size in PORTAL_CODE_GROUPS:
        parts.append(n[i : i + size])
        i += size
    return "-".join(p for p in parts if p)


def generate_access_code() -> str:
    total = sum(PORTAL_CODE_GROUPS)
    chars = [secrets.choice(PORTAL_CODE_ALPHABET) for _ in range(total)]
    return format_access_code("".join(chars))


def hash_access_code(code: str) -> str:
    normalized = normalize_access_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def store_portal_access_code(row: ContactPortalAccess, code: str) -> None:
    from app.email_crypt import encrypt_password

    formatted = format_access_code(code)
    row.code_sha256 = hash_access_code(formatted)
    row.code_enc = encrypt_password(formatted)


def staff_portal_access_code(row: ContactPortalAccess) -> str | None:
    from app.email_crypt import decrypt_password

    enc = (row.code_enc or "").strip()
    if not enc:
        return None
    try:
        return decrypt_password(enc).strip() or None
    except Exception:
        return None


def file_folder_in_grant(*, file_folder: str, grant_folder: str) -> bool:
    gf = sanitize_folder_path(grant_folder)
    ff = sanitize_folder_path(file_folder or "")
    if gf == ff:
        return True
    if gf and ff.startswith(gf + "/"):
        return True
    return False


def grant_is_active(grant: ContactPortalGrant, *, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if grant.expires_at is not None:
        exp = grant.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now >= exp:
            return False
    return True


def portal_access_is_active(row: ContactPortalAccess, *, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if not row.enabled:
        return False
    if row.expires_at is not None:
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now >= exp:
            return False
    if row.locked_until is not None:
        locked = row.locked_until
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        if now < locked:
            return False
    return True


def get_portal_access_by_code(db: Session, access_code: str) -> ContactPortalAccess | None:
    digest = hash_access_code(access_code)
    return db.execute(select(ContactPortalAccess).where(ContactPortalAccess.code_sha256 == digest)).scalar_one_or_none()


def list_active_grants_for_contact(db: Session, contact_id: uuid.UUID) -> list[ContactPortalGrant]:
    now = utcnow()
    rows = db.execute(select(ContactPortalGrant).where(ContactPortalGrant.contact_id == contact_id)).scalars().all()
    return [g for g in rows if grant_is_active(g, now=now)]


def get_grant_for_contact(db: Session, *, contact_id: uuid.UUID, grant_id: uuid.UUID) -> ContactPortalGrant:
    grant = db.get(ContactPortalGrant, grant_id)
    if not grant or grant.contact_id != contact_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Area not found")
    if not grant_is_active(grant):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This area is no longer available")
    from app.portal_case import require_case_portal_enabled

    require_case_portal_enabled(db, grant.case_id)
    return grant


def list_grant_files(db: Session, grant: ContactPortalGrant) -> list[File]:
    rows = (
        db.execute(
            select(File).where(
                File.case_id == grant.case_id,
                File.oo_compose_pending.is_(False),
                File.category != FileCategory.system,
            )
        )
        .scalars()
        .all()
    )
    out: list[File] = []
    for row in rows:
        if file_folder_in_grant(file_folder=row.folder_path or "", grant_folder=grant.folder_path):
            out.append(row)
    out.sort(key=lambda f: (f.folder_path or "", f.original_filename.lower()))
    return out


def get_grant_file(db: Session, grant: ContactPortalGrant, file_id: uuid.UUID) -> File:
    row = db.get(File, file_id)
    if not row or row.case_id != grant.case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.category == FileCategory.system or row.oo_compose_pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not file_folder_in_grant(file_folder=row.folder_path or "", grant_folder=grant.folder_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return row


def get_portal_grant_file(
    db: Session,
    grant: ContactPortalGrant,
    contact_id: uuid.UUID,
    file_id: uuid.UUID,
) -> File:
    """Folder grant access, or delivery-scoped access for sent portal quotes."""
    row = db.get(File, file_id)
    if not row or row.case_id != grant.case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.category == FileCategory.system or row.oo_compose_pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if file_folder_in_grant(file_folder=row.folder_path or "", grant_folder=grant.folder_path):
        return row
    from app.quote_portal_service import quote_delivery_grants_file_access

    if quote_delivery_grants_file_access(
        db,
        contact_id=contact_id,
        case_id=grant.case_id,
        file_id=file_id,
    ):
        return row
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


def default_grant_label(db: Session, grant: ContactPortalGrant) -> str:
    if grant.label and grant.label.strip():
        return grant.label.strip()
    case = db.get(Case, grant.case_id)
    matter = case.title.strip() if case and case.title else "Documents"
    folder = sanitize_folder_path(grant.folder_path)
    if folder:
        leaf = folder.split("/")[-1]
        return f"{matter} — {leaf}"
    return matter


def record_portal_auth_failure(db: Session, row: ContactPortalAccess) -> None:
    row.failed_attempts = int(row.failed_attempts or 0) + 1
    if row.failed_attempts >= PORTAL_MAX_FAILED_ATTEMPTS:
        row.locked_until = utcnow() + timedelta(minutes=PORTAL_LOCKOUT_MINUTES)
        row.failed_attempts = 0
    row.updated_at = utcnow()
    db.add(row)
    db.commit()


def record_portal_auth_success(db: Session, row: ContactPortalAccess) -> None:
    row.failed_attempts = 0
    row.locked_until = None
    row.last_login_at = utcnow()
    row.updated_at = utcnow()
    db.add(row)
    db.commit()


def ensure_upload_folder_allowed(*, grant: ContactPortalGrant, folder: str) -> str:
    if not grant.can_upload:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload is not allowed for this area")
    target = sanitize_folder_path(folder)
    grant_root = sanitize_folder_path(grant.folder_path)
    if grant_root and target != grant_root and not target.startswith(grant_root + "/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload folder is outside this area")
    if not grant_root and target:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload folder is outside this area")
    return target


def grant_folder_display_name(grant: ContactPortalGrant) -> str:
    if grant.label and grant.label.strip():
        return grant.label.strip()
    folder = sanitize_folder_path(grant.folder_path)
    if not folder:
        return "Documents"
    return folder.split("/")[-1]


def contact_display_name(contact: Contact) -> str:
    return (contact.name or "").strip() or "Client"


def relative_folder_under_grant(*, grant_folder: str, absolute_folder: str) -> str:
    """Return folder path relative to grant root for display (may be empty)."""
    gf = sanitize_folder_path(grant_folder)
    ff = sanitize_folder_path(absolute_folder or "")
    if gf == ff:
        return ""
    if gf and ff.startswith(gf + "/"):
        return ff[len(gf) + 1 :]
    if not gf:
        return ff
    return ff


def browse_grant_folder(
    db: Session,
    grant: ContactPortalGrant,
    *,
    subfolder: str = "",
) -> tuple[str, list[str], list[File]]:
    """Return (relative_subfolder, immediate_child_folder_names, files_in_current_folder)."""
    grant_root = sanitize_folder_path(grant.folder_path)
    rel = sanitize_folder_path(subfolder)
    if grant_root:
        current = sanitize_folder_path(f"{grant_root}/{rel}" if rel else grant_root)
    else:
        current = rel

    if not file_folder_in_grant(file_folder=current, grant_folder=grant_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Folder is outside this area")

    all_files = list_grant_files(db, grant)
    current_norm = sanitize_folder_path(current)
    files_here = [f for f in all_files if sanitize_folder_path(f.folder_path or "") == current_norm]
    child_names: set[str] = set()
    prefix = f"{current_norm}/" if current_norm else ""
    for f in all_files:
        fp = sanitize_folder_path(f.folder_path or "")
        if current_norm:
            if fp != current_norm and not fp.startswith(prefix):
                continue
            rest = fp[len(prefix) :] if fp.startswith(prefix) else ""
        else:
            if not fp:
                continue
            rest = fp
        if not rest:
            continue
        child_names.add(rest.split("/")[0])
    return rel, sorted(child_names, key=str.lower), files_here


PORTAL_OTP_TTL_MINUTES = 15


def _otp_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def issue_portal_login_otp(db: Session, contact_id: uuid.UUID) -> str:
    code = f"{secrets.randbelow(900000) + 100000:06d}"
    row = PortalLoginOtp(
        contact_id=contact_id,
        code_sha256=_otp_hash(code),
        expires_at=utcnow() + timedelta(minutes=PORTAL_OTP_TTL_MINUTES),
    )
    db.add(row)
    db.flush()
    return code


def verify_portal_login_otp(db: Session, contact_id: uuid.UUID, code: str) -> bool:
    digest = _otp_hash(code)
    now = utcnow()
    row = (
        db.execute(
            select(PortalLoginOtp)
            .where(
                PortalLoginOtp.contact_id == contact_id,
                PortalLoginOtp.code_sha256 == digest,
                PortalLoginOtp.used_at.is_(None),
            )
            .order_by(PortalLoginOtp.created_at.desc())
        )
        .scalars()
        .first()
    )
    if row is None:
        return False
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now >= exp:
        return False
    row.used_at = now
    db.add(row)
    return True


def find_portal_contact_by_email(db: Session, email: str) -> Contact | None:
    addr = (email or "").strip().lower()
    if not addr:
        return None
    rows = db.execute(select(Contact)).scalars().all()
    for c in rows:
        if (c.email or "").strip().lower() == addr:
            access = db.execute(
                select(ContactPortalAccess).where(ContactPortalAccess.contact_id == c.id)
            ).scalar_one_or_none()
            if access and portal_access_is_active(access):
                return c
    return None

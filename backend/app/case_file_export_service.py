"""Case file ZIP export helpers (matter export + folder download)."""

from __future__ import annotations

import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from urllib.parse import unquote

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.audit import log_event
from app.deps import require_case_access
from app.file_storage import FILES_ROOT, ensure_files_root, path_is_under_files_root, sanitize_folder_path
from app.models import Case as CaseRow
from app.models import CaseLockMode, CaseStatus, File as DbFile, MatterHeadType, MatterSubType, User


def _safe_zip_path_component(name: str) -> str:
    """Single path segment safe for zip archive (decoded, no slashes)."""
    try:
        n = unquote(name or "")
    except Exception:
        n = name or ""
    n = n.replace("\\", "_").replace("/", "_").replace("\0", "").strip() or "_"
    if n in (".", ".."):
        n = "_"
    return n


def _zip_arc_for_file_row(*, prefix: str, row: DbFile) -> str:
    fp = (row.folder_path or "").strip()
    leaf = _safe_zip_path_component(row.original_filename)
    if fp == prefix:
        return leaf
    prefix_slash = f"{prefix}/"
    if fp.startswith(prefix_slash):
        rel = fp[len(prefix_slash) :]
        segs = [_safe_zip_path_component(s) for s in rel.split("/") if s]
        if not segs:
            return leaf
        return "/".join(segs + [leaf])
    raise ValueError("file row is not under the requested folder prefix")


def _unique_zip_name(taken: set[str], want: str) -> str:
    if want not in taken:
        taken.add(want)
        return want
    n = 2
    while True:
        if "/" in want:
            parent, base = want.rsplit("/", 1)
            stem = Path(base).stem
            suf = Path(base).suffix
            cand = f"{parent}/{stem}_{n}{suf}"
        else:
            stem = Path(want).stem
            suf = Path(want).suffix
            cand = f"{stem}_{n}{suf}"
        if cand not in taken:
            taken.add(cand)
            return cand
        n += 1


def _unlink_if_exists(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _format_case_status_label(status: CaseStatus) -> str:
    labels = {
        CaseStatus.open: "Active",
        CaseStatus.closed: "Closed",
        CaseStatus.archived: "Archived",
        CaseStatus.quote: "Quote",
        CaseStatus.quote_closed: "Closed",
        CaseStatus.post_completion: "Post-completion",
    }
    return labels.get(status, str(status.value if hasattr(status, "value") else status))


def _matter_type_display_line(*, sub_name: str | None, head_name: str | None) -> str:
    def _clean(s: str | None) -> str:
        t = (s or "").strip()
        if not t or t in ("—", "-", "–"):
            return ""
        return t

    head = _clean(head_name)
    sub = _clean(sub_name)
    if head and sub and head.lower() == sub.lower():
        return head
    if head and sub:
        marker = " — "
        j = head.find(marker)
        if j >= 0:
            tail = head[j + len(marker) :].strip()
            if tail and tail.lower() == sub.lower():
                return head
    parts = [p for p in (head, sub) if p]
    out = " — ".join(parts)
    while " — — " in out:
        out = out.replace(" — — ", " — ")
    return out or "—"


def _case_lock_display(*, lock_mode: CaseLockMode, is_locked: bool) -> str:
    if lock_mode == CaseLockMode.allow_list:
        return "Locked"
    if lock_mode == CaseLockMode.open_by_default:
        return "Locked" if is_locked else "Unlocked"
    return "Unlocked"


def _matter_names_for_case(case: CaseRow, db: Session) -> tuple[str | None, str | None]:
    if case.matter_sub_type_id:
        sub = db.get(MatterSubType, case.matter_sub_type_id)
        if not sub:
            return None, None
        head = db.get(MatterHeadType, sub.head_type_id)
        return sub.name, (head.name if head else None)
    if case.matter_head_type_id:
        head = db.get(MatterHeadType, case.matter_head_type_id)
        return None, (head.name if head else None)
    return None, None


def _case_details_export_text(case: CaseRow, db: Session) -> str:
    sub_name, head_name = _matter_names_for_case(case, db)
    fee_earner = db.get(User, case.fee_earner_user_id)
    fee_label = (fee_earner.display_name if fee_earner else "") or "—"
    lines = [
        "Case details",
        "",
        f"Reference: {case.case_number}",
        f"Client: {case.client_name or '—'}",
        f"Matter type: {_matter_type_display_line(sub_name=sub_name, head_name=head_name)}",
        f"Description: {case.title}",
        f"Status: {_format_case_status_label(case.status)}",
        f"Fee earner: {fee_label}",
        f"Lock: {_case_lock_display(lock_mode=case.lock_mode, is_locked=case.is_locked)}",
    ]
    return "\n".join(lines) + "\n"


def _zip_arc_for_case_export(row: DbFile) -> str:
    fp = (row.folder_path or "").strip()
    leaf = _safe_zip_path_component(row.original_filename)
    if not fp:
        return leaf
    segs = [_safe_zip_path_component(s) for s in fp.split("/") if s]
    return "/".join(segs + [leaf])


def download_case_export_zip(
    case_id: uuid.UUID,
    user: User,
    db: Session,
) -> FileResponse:
    """Download all matter files plus ``case-details.txt`` (Case details panel) as a zip."""
    require_case_access(case_id, user, db)
    case = db.get(CaseRow, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    ensure_files_root()

    rows = (
        db.execute(
            select(DbFile).where(
                DbFile.case_id == case_id,
                DbFile.oo_compose_pending.is_(False),
            )
        )
        .scalars()
        .all()
    )
    file_rows = [r for r in rows if (r.mime_type or "") != "application/x-directory"]

    safe_ref = _safe_zip_path_component(case.case_number) or "matter"
    details_name = "case-details.txt"
    arc_taken: set[str] = {details_name}

    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(details_name, _case_details_export_text(case, db).encode("utf-8"))
            for row in file_rows:
                abs_path = (FILES_ROOT / row.storage_path).resolve()
                if not path_is_under_files_root(abs_path) or not abs_path.is_file():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File missing on disk: {row.original_filename}",
                    )
                arc = _zip_arc_for_case_export(row).replace("\\", "/")
                if arc.startswith("/") or arc.startswith("../") or "/../" in arc:
                    continue
                arc = _unique_zip_name(arc_taken, arc)
                zf.write(abs_path, arcname=arc)

        log_event(
            db,
            actor_user_id=user.id,
            action="case.export_zip",
            entity_type="case",
            entity_id=str(case_id),
            meta={"file_count": len(file_rows)},
        )

        return FileResponse(
            path=tmp,
            media_type="application/zip",
            filename=f"{safe_ref}-export.zip",
            content_disposition_type="attachment",
            background=BackgroundTask(_unlink_if_exists, tmp),
        )
    except HTTPException:
        if tmp:
            _unlink_if_exists(tmp)
        raise
    except Exception:
        if tmp:
            _unlink_if_exists(tmp)
        raise


def download_case_folder_zip(
    case_id: uuid.UUID,
    folder_path: str,
    user: User,
    db: Session,
) -> FileResponse:
    """Download all non-folder files under ``folder_path`` as a single .zip (relative paths preserved)."""
    require_case_access(case_id, user, db)
    prefix = sanitize_folder_path(folder_path)
    if not prefix:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="folder_path is required")
    ensure_files_root()

    like_prefix = f"{prefix}/%"
    rows = (
        db.execute(
            select(DbFile).where(
                DbFile.case_id == case_id,
                DbFile.oo_compose_pending.is_(False),
                or_(DbFile.folder_path == prefix, DbFile.folder_path.like(like_prefix)),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    parts = [p for p in prefix.split("/") if p]
    leaf_enc = parts[-1] if parts else ""
    zip_label = _safe_zip_path_component(leaf_enc) if leaf_enc else "folder"
    if zip_label == "_":
        zip_label = "folder"

    file_rows = [r for r in rows if (r.mime_type or "") != "application/x-directory"]
    arc_taken: set[str] = set()
    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for row in file_rows:
                abs_path = (FILES_ROOT / row.storage_path).resolve()
                if not path_is_under_files_root(abs_path) or not abs_path.is_file():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File missing on disk: {row.original_filename}",
                    )
                try:
                    arc = _zip_arc_for_file_row(prefix=prefix, row=row)
                except ValueError:
                    continue
                arc = arc.replace("\\", "/")
                if arc.startswith("/") or arc.startswith("../") or "/../" in arc:
                    continue
                arc = _unique_zip_name(arc_taken, arc)
                zf.write(abs_path, arcname=arc)

        log_event(
            db,
            actor_user_id=user.id,
            action="case.folder.download_zip",
            entity_type="case",
            entity_id=str(case_id),
            meta={"folder_path": prefix, "file_count": len(file_rows)},
        )

        return FileResponse(
            path=tmp,
            media_type="application/zip",
            filename=f"{zip_label}.zip",
            content_disposition_type="attachment",
            background=BackgroundTask(_unlink_if_exists, tmp),
        )
    except HTTPException:
        if tmp:
            _unlink_if_exists(tmp)
        raise
    except Exception:
        if tmp:
            _unlink_if_exists(tmp)
        raise

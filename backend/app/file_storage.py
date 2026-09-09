from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


FILES_ROOT = Path(_require_env("FILES_ROOT")).resolve()


@dataclass(frozen=True)
class StoredFilePaths:
    abs_path: Path
    rel_path: str
    folder_path: str


def ensure_files_root() -> None:
    FILES_ROOT.mkdir(parents=True, exist_ok=True)


def assert_under_files_root(abs_path: Path) -> Path:
    """Resolve and ensure ``abs_path`` is contained under ``FILES_ROOT`` (not a string prefix)."""
    resolved = abs_path.resolve()
    if not resolved.is_relative_to(FILES_ROOT):
        raise RuntimeError("Resolved path escaped FILES_ROOT")
    return resolved


def path_is_under_files_root(abs_path: Path) -> bool:
    try:
        assert_under_files_root(abs_path)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def write_bytes_atomic(abs_path: Path, data: bytes) -> None:
    """Write via a sibling ``.partial`` file then ``os.replace`` (crash-safe promote)."""
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = abs_path.with_name(abs_path.name + ".partial")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, abs_path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def stream_upload_to_path(abs_path: Path, fileobj, *, max_bytes: int) -> int:
    """Stream ``fileobj`` to ``abs_path`` atomically; raise ValueError if over ``max_bytes``."""
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = abs_path.with_name(abs_path.name + ".partial")
    size = 0
    try:
        with tmp.open("wb") as f:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"Upload exceeds maximum size of {max_bytes} bytes")
                f.write(chunk)
        os.replace(tmp, abs_path)
        return size
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def unlink_stored_file(abs_path: Path) -> None:
    """Best-effort delete of a path that must stay under ``FILES_ROOT`` (orphan cleanup)."""
    try:
        assert_under_files_root(abs_path).unlink(missing_ok=True)
    except (OSError, RuntimeError, ValueError):
        pass


def _sanitize_folder_path(folder_path: str) -> str:
    # Accept user-provided folder path as a slash-separated relative string.
    # We do not allow absolute paths, backtracking (..), or traversal components.
    p = PurePosixPath(folder_path or "")
    parts: list[str] = []
    for part in p.parts:
        if part in ("", ".", "/"):
            continue
        if part == "..":
            raise ValueError("Invalid folder path")
        parts.append(part)
    return "/".join(parts)


def sanitize_folder_path(folder_path: str) -> str:
    # Public wrapper used by routers.
    return _sanitize_folder_path(folder_path)


def decode_folder_path_segment(segment: str) -> str:
    from urllib.parse import unquote

    cur = segment
    for _ in range(6):
        try:
            nxt = unquote(cur)
            if nxt == cur:
                break
            cur = nxt
        except Exception:
            break
    return cur


def decode_folder_path_for_display(path: str) -> str:
    parts = [p for p in (path or "").split("/") if p]
    return "/".join(decode_folder_path_segment(p) for p in parts)


def firm_letterhead_file_paths(*, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("firm") / "letterhead" / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def firm_portal_logo_file_paths(*, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("firm") / "portal-logo" / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def firm_default_signature_file_paths(*, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("firm") / "default-signature" / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def precedent_file_paths(*, precedent_id: uuid.UUID, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("precedents") / str(precedent_id) / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def fee_scale_file_paths(*, fee_scale_id: uuid.UUID, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("fee_scales") / str(fee_scale_id) / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def firm_quote_letterhead_file_paths(*, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("firm") / "quote_letterhead" / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def firm_invoice_template_file_paths(*, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("firm") / "invoice_template" / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def user_signature_file_paths(*, user_id: uuid.UUID, file_id: uuid.UUID, original_filename: str) -> StoredFilePaths:
    safe_name = Path(original_filename).name
    rel = Path("users") / str(user_id) / "signature" / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path="")


def case_file_paths(*, case_id: uuid.UUID, file_id: uuid.UUID, original_filename: str, folder_path: str = "") -> StoredFilePaths:
    # Keep user-provided filename only as a suffix; never trust it as a path.
    safe_name = Path(original_filename).name

    sanitized_folder = _sanitize_folder_path(folder_path)
    base = Path("cases") / str(case_id)
    if sanitized_folder:
        rel = base / Path(sanitized_folder) / f"{file_id}__{safe_name}"
    else:
        rel = base / f"{file_id}__{safe_name}"
    abs_path = assert_under_files_root(FILES_ROOT / rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return StoredFilePaths(abs_path=abs_path, rel_path=str(rel), folder_path=sanitized_folder)


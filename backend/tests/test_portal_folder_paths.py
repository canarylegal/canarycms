"""Portal folder path validation (CL-01)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.file_storage import sanitize_folder_path
from app.portal_service import browse_grant_folder, ensure_upload_folder_allowed


def test_sanitize_rejects_dotdot() -> None:
    with pytest.raises(ValueError, match="Invalid folder path"):
        sanitize_folder_path("../private")
    with pytest.raises(ValueError, match="Invalid folder path"):
        sanitize_folder_path("shared/../private")


def test_sanitize_rejects_absolute() -> None:
    with pytest.raises(ValueError, match="Invalid folder path"):
        sanitize_folder_path("/private")


def test_sanitize_allows_relative_subfolder() -> None:
    assert sanitize_folder_path("shared") == "shared"
    assert sanitize_folder_path("shared/client-uploads") == "shared/client-uploads"
    assert sanitize_folder_path("") == ""


def test_browse_rejects_traversal_with_400() -> None:
    grant = SimpleNamespace(folder_path="shared", can_download=True, can_upload=True)
    with pytest.raises(HTTPException) as ei:
        browse_grant_folder(None, grant, subfolder="../private")  # type: ignore[arg-type]
    assert ei.value.status_code == 400
    assert "Invalid folder path" in str(ei.value.detail)


def test_browse_rejects_absolute_with_400() -> None:
    grant = SimpleNamespace(folder_path="shared", can_download=True, can_upload=True)
    with pytest.raises(HTTPException) as ei:
        browse_grant_folder(None, grant, subfolder="/private")  # type: ignore[arg-type]
    assert ei.value.status_code == 400


def test_upload_rejects_traversal_with_400() -> None:
    grant = SimpleNamespace(folder_path="shared", can_upload=True)
    with pytest.raises(HTTPException) as ei:
        ensure_upload_folder_allowed(grant=grant, folder="../private")  # type: ignore[arg-type]
    assert ei.value.status_code == 400
    assert "Invalid folder path" in str(ei.value.detail)


def test_upload_allows_grant_root_and_child() -> None:
    grant = SimpleNamespace(folder_path="shared", can_upload=True)
    assert ensure_upload_folder_allowed(grant=grant, folder="shared") == "shared"  # type: ignore[arg-type]
    assert (
        ensure_upload_folder_allowed(grant=grant, folder="shared/inbox") == "shared/inbox"  # type: ignore[arg-type]
    )

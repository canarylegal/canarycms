"""Deployment toggles (env-only; defaults preserve upstream behaviour)."""

from __future__ import annotations

import os

from app.onlyoffice_ds_version import onlyoffice_ds_major


def _truthy_env(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def open_pdf_in_onlyoffice() -> bool:
    """When true, case PDFs use ONLYOFFICE instead of the browser blob viewer."""
    return _truthy_env("CANARY_OPEN_PDF_IN_ONLYOFFICE")


def onlyoffice_pdf_editor_types() -> tuple[str, str]:
    """``(documentType, fileType)`` for PDFs.

    - DS 7.x: ``word`` + ``pdf`` (annotation viewer; saves as copy only).
    - DS 8.0+: ``pdf`` + ``pdf`` (native editor; in-place save via callback from 9.0.3+).
    """
    mode = (os.getenv("CANARY_ONLYOFFICE_PDF_DOCUMENT_TYPE") or "auto").strip().lower()
    if mode == "word":
        return ("word", "pdf")
    if mode == "pdf":
        return ("pdf", "pdf")
    major = onlyoffice_ds_major()
    if major >= 8:
        return ("pdf", "pdf")
    return ("word", "pdf")
